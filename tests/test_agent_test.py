from __future__ import annotations

import contextlib
import copy
import io
import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

from foundry_databricks_genie.agent_test import execute_agent_test, inspect_agent, invoke_existing
from foundry_databricks_genie.cli import main
from foundry_databricks_genie.config import Configuration, ConfigurationError


CONFIG = Configuration(
    "https://example.services.ai.azure.com/api/projects/demo",
    "https://example.azuredatabricks.net", "space_123-abc", "genie", "portal-toolbox",
    foundry_connection_mode="existing-oauth",
)
URL = CONFIG.foundry_project_endpoint + "/toolboxes/portal-toolbox/versions/2/mcp?api-version=v1"
ENV = """\
FOUNDRY_PROJECT_ENDPOINT=https://example.services.ai.azure.com/api/projects/demo
DATABRICKS_WORKSPACE_HOST=https://example.azuredatabricks.net
DATABRICKS_GENIE_SPACE_ID=space_123-abc
FOUNDRY_CONNECTION_NAME=genie
FOUNDRY_TOOLBOX_NAME=portal-toolbox
FOUNDRY_TEST_AGENT_NAME=portal-agent
FOUNDRY_CONNECTION_MODE=existing-oauth
"""


def saved_agent():
    return {
        "state": "enabled",
        "versions": {"latest": {
            "version": "5", "status": "active", "metadata": {},
            "definition": {
                "kind": "prompt", "model": "portal-model", "instructions": "Preserve me.",
                "tools": [{
                    "type": "mcp", "server_label": "portal_label", "server_url": URL,
                    "require_approval": "never",
                }],
            },
        }},
        "agent_endpoint": {"version_selector": {"version_selection_rules": [
            {"type": "FixedRatio", "agent_version": "@latest", "traffic_percentage": 100}
        ]}},
    }


class ExistingAgentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.project = Mock()
        self.project.get_openai_client.return_value = MagicMock()
        self.agent = saved_agent()
        self.box = {"tools": [{
            "type": "mcp", "server_url": CONFIG.genie_mcp_endpoint,
            "project_connection_id": "genie",
        }]}
        self.project.agents.get.return_value.as_dict.side_effect = lambda: copy.deepcopy(self.agent)
        self.project.toolboxes.get_version.return_value.as_dict.side_effect = lambda: copy.deepcopy(self.box)
        self.connection = Mock(id="/projects/demo/connections/genie", target=CONFIG.genie_mcp_endpoint)
        self.connection.name = "genie"
        self.connection.as_dict.return_value = {"credentials": {"type": "OAuth2"}}
        self.project.connections.get.return_value = self.connection

    def assert_no_mutations(self) -> None:
        for operation in (self.project.agents, self.project.toolboxes, self.project.connections):
            operation.create_version.assert_not_called()
            operation.update.assert_not_called()
            operation.delete.assert_not_called()
        self.project.deployments.get.assert_not_called()

    def test_native_toolbox_without_connection_or_ownership_metadata_is_accepted(self) -> None:
        target = inspect_agent(self.project, CONFIG, "portal-agent")
        self.assertEqual(target.agent_version, "5")
        self.assertEqual(target.toolbox_version, "2")
        self.assertEqual(target.model, "portal-model")
        self.assertEqual(target.server_label, "portal_label")
        self.project.toolboxes.get_version.assert_called_once_with("portal-toolbox", "2")
        self.project.toolboxes.get.assert_not_called()
        self.project.connections.get.assert_called_once_with("genie", include_credentials=False)
        self.assert_no_mutations()

    def test_wrong_project_unversioned_and_malformed_urls_fail_before_invocation(self) -> None:
        for target in (
            URL.replace("example.services", "different.services"),
            URL.replace("portal-toolbox", "other"),
            URL.replace("/versions/2", ""),
            URL.replace("https:", "http:"),
            URL.replace("?api-version=v1", "?api-version=v1&extra=1"),
            URL + "&api-version=v1", URL + "#fragment",
            URL.replace("example.services", "user@example.services"),
        ):
            with self.subTest(target=target):
                self.agent = saved_agent()
                self.agent["versions"]["latest"]["definition"]["tools"][0]["server_url"] = target
                with self.assertRaises(ConfigurationError):
                    invoke_existing(self.project, CONFIG, "portal-agent", "test", approve_tools=True)
                self.project.get_openai_client.assert_not_called()
        self.assert_no_mutations()

    def test_pinned_toolbox_must_match_expected_oauth_connection(self) -> None:
        original = copy.deepcopy(self.box)
        changes = [
            {"tools": []}, {"tools": original["tools"] * 2},
            {**original, "skills": [{"name": "unrelated"}]},
            {"tools": [{**original["tools"][0], "project_connection_id": "/projects/other/connections/genie"}]},
            {"tools": [{**original["tools"][0], "server_url": "https://other.example"}]},
            {"tools": [{**original["tools"][0], "headers": {"x-test": "private-canary"}}]},
        ]
        for changed in changes:
            with self.subTest(changed=changed), self.assertRaises(ConfigurationError):
                self.box = changed
                inspect_agent(self.project, CONFIG, "portal-agent")
        self.box = original
        self.connection.as_dict.return_value = {"credentials": {"type": "CustomKeys"}}
        with self.assertRaises(ConfigurationError):
            inspect_agent(self.project, CONFIG, "portal-agent")
        self.assert_no_mutations()

    def test_existing_binding_is_checked_when_present_but_never_created(self) -> None:
        self.agent["versions"]["latest"]["definition"]["tools"][0]["project_connection_id"] = "access"
        binding = Mock(id="/projects/demo/connections/access", target=URL)
        binding.name = "access"
        self.project.connections.get.side_effect = lambda name, **_: self.connection if name == "genie" else binding
        inspect_agent(self.project, CONFIG, "portal-agent")
        binding.target = "https://other.example"
        with self.assertRaises(ConfigurationError):
            inspect_agent(self.project, CONFIG, "portal-agent")
        self.assert_no_mutations()

    def test_extra_agent_tools_skills_harness_or_headers_are_rejected(self) -> None:
        original = saved_agent()["versions"]["latest"]["definition"]
        for change in (
            {"kind": "hosted"}, {"skills": [{"name": "other"}]}, {"harness": {"type": "other"}},
            {"tools": original["tools"] * 2},
            {"tools": [{**original["tools"][0], "headers": {"x-test": "private-canary"}}]},
        ):
            self.agent = saved_agent()
            self.agent["versions"]["latest"]["definition"].update(change)
            with self.subTest(change=change), self.assertRaises(ConfigurationError):
                inspect_agent(self.project, CONFIG, "portal-agent")

    def test_unconditional_tool_execution_requires_explicit_test_authorization(self) -> None:
        with self.assertRaisesRegex(ConfigurationError, "--approve-tools"):
            invoke_existing(self.project, CONFIG, "portal-agent", "test")
        self.project.get_openai_client.assert_not_called()

    def test_invocation_uses_saved_label_and_preserves_every_resource(self) -> None:
        before = copy.deepcopy(self.agent)
        with patch("foundry_databricks_genie.agent_test.run_smoke", return_value=0) as smoke:
            with contextlib.redirect_stdout(io.StringIO()) as output:
                result = invoke_existing(
                    self.project, CONFIG, "portal-agent", "private-question",
                    approve_tools=True, non_interactive=True,
                )
        self.assertEqual(result, 0)
        self.assertEqual(smoke.call_args.kwargs["server_label"], "portal_label")
        self.assertEqual(self.project.agents.get.call_count, 2)
        self.assertEqual(self.agent, before)
        self.assertNotIn("private-question", output.getvalue())
        self.assert_no_mutations()

    def test_agent_version_change_during_invocation_fails_verification(self) -> None:
        def mutate(*args, **kwargs):
            self.agent["versions"]["latest"]["version"] = "6"
            return 0

        with patch("foundry_databricks_genie.agent_test.run_smoke", side_effect=mutate):
            with contextlib.redirect_stdout(io.StringIO()) as output:
                with self.assertRaisesRegex(ConfigurationError, "changed during"):
                    invoke_existing(self.project, CONFIG, "portal-agent", "test", approve_tools=True)
        self.assertNotIn("PASS:", output.getvalue())
        self.assert_no_mutations()

    def test_consent_and_failure_results_are_propagated(self) -> None:
        for code in (3, 4):
            with patch("foundry_databricks_genie.agent_test.run_smoke", return_value=code):
                with contextlib.redirect_stdout(io.StringIO()) as output:
                    self.assertEqual(invoke_existing(
                        self.project, CONFIG, "portal-agent", "test", approve_tools=True
                    ), code)
            self.assertNotIn("PASS:", output.getvalue())


class ExistingAgentCliTests(unittest.TestCase):
    def test_cli_needs_no_model_binding_or_bootstrap_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env = Path(directory) / "config.env"
            question = Path(directory) / "question.txt"
            # Even invalid bootstrap-only fields must not affect existing-agent testing.
            env.write_text(ENV + "FOUNDRY_MODEL_DEPLOYMENT=\nFOUNDRY_TOOLBOX_CONNECTION_NAME=<unused>\n")
            question.write_text("synthetic-question")
            with patch.dict(os.environ, {}, clear=True):
                with patch("foundry_databricks_genie.agent_test.execute_agent_test", return_value=3) as execute:
                    with patch("foundry_databricks_genie.cli.setup") as provision:
                        result = main([
                            "test-agent", "--env-file", str(env), "--question-file", str(question),
                            "--approve-tools", "--non-interactive",
                        ])
            self.assertEqual(result, 3)
            self.assertEqual(execute.call_args.args[1:3], ("portal-agent", "synthetic-question"))
            self.assertTrue(execute.call_args.kwargs["approve_tools"])
            provision.assert_not_called()

    def test_custom_foundry_host_rejected_before_credentials(self) -> None:
        c = replace(CONFIG, foundry_project_endpoint="https://other.example/api/projects/demo")
        with self.assertRaisesRegex(ConfigurationError, "public-Azure"):
            execute_agent_test(c, "portal-agent", "question")


if __name__ == "__main__":
    unittest.main()
