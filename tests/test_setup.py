from __future__ import annotations

import contextlib
import io
import json
import subprocess
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from foundry_databricks_genie.config import Configuration, ConfigurationError
from foundry_databricks_genie.setup import (
    assert_connection,
    assert_toolbox_connections,
    parse_json,
    render_toolbox,
    resource_exists,
    setup,
)


class SetupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.output = Path(self.directory.name) / "toolbox.yaml"
        self.config = Configuration(
            "https://example.services.ai.azure.com/api/projects/demo",
            "https://example.azuredatabricks.net",
            "space_123-abc", "databricks-genie", "databricks-genie-toolbox",
        )
        self.names = [{"name": self.config.foundry_connection_name}]
        self.toolboxes = [{"name": self.config.foundry_toolbox_name}]

    def connection(self, **changes: object) -> dict[str, object]:
        return {
            "name": self.config.foundry_connection_name,
            "properties": {
                "target": self.config.genie_mcp_endpoint,
                "category": "RemoteTool", "authType": "OAuth2",
                "scopes": list(self.config.required_oauth_scopes),
                **changes,
            },
        }

    def run_setup(self, documents: list[object], *, replace_connection: bool = False):
        results = [subprocess.CompletedProcess([], 0, json.dumps(doc), "") for doc in documents]
        with patch("foundry_databricks_genie.setup.shutil.which", return_value="azd"):
            with patch("foundry_databricks_genie.setup.subprocess.run", side_effect=results) as run:
                with contextlib.redirect_stdout(io.StringIO()):
                    setup(self.config, self.output, replace_connection=replace_connection)
        return run

    def test_creates_managed_connection_and_toolbox_and_verifies_them(self) -> None:
        run = self.run_setup([[], [], {}, self.connection(), {}, self.names])
        commands = [call.args[0] for call in run.call_args_list]
        self.assertEqual(len(commands), 6)
        create = commands[2]
        self.assertIn("foundrydatabricksmcp", create)
        self.assertNotIn("--scopes", create)
        self.assertNotIn("--force", create)
        self.assertIn(self.config.genie_mcp_endpoint, create)
        self.assertEqual(commands[3][2:4], ["connection", "show"])
        self.assertEqual(commands[5][2:5], ["toolbox", "connection", "list"])
        self.assertEqual(self.output.read_text(), render_toolbox("databricks-genie"))
        for command in commands:
            self.assertIn("--no-prompt", command)
            self.assertNotIn("--show-credentials", command)

    def test_preserves_matching_resources_without_writes(self) -> None:
        run = self.run_setup([self.names, self.toolboxes, self.connection(), self.names])
        for call in run.call_args_list:
            self.assertNotIn("create", call.args[0])

    def test_genie_one_reuses_existing_oauth_and_only_creates_toolbox(self) -> None:
        self.config = replace(
            self.config, databricks_integration_mode="genie-one",
            databricks_workspace_id="123", databricks_genie_space_id="",
            foundry_connection_mode="existing-oauth",
        )
        run = self.run_setup([self.names, [], self.connection(), {}, self.names])
        commands = [call.args[0] for call in run.call_args_list]
        self.assertEqual(commands[3][2:4], ["toolbox", "create"])
        self.assertFalse(any(command[2:4] == ["connection", "create"] for command in commands))

    def test_missing_existing_oauth_connection_never_creates_resources(self) -> None:
        self.config = replace(self.config, foundry_connection_mode="existing-oauth")
        with self.assertRaisesRegex(ConfigurationError, "not found"):
            self.run_setup([[], []])
        self.assertFalse(self.output.exists())

    def test_existing_oauth_cannot_be_replaced(self) -> None:
        self.config = replace(self.config, foundry_connection_mode="existing-oauth")
        with patch("foundry_databricks_genie.setup.subprocess.run") as run:
            with self.assertRaisesRegex(ConfigurationError, "Replacement is not allowed"):
                setup(self.config, self.output, replace_connection=True)
            run.assert_not_called()

    def test_genie_one_managed_connection_is_never_created(self) -> None:
        self.config = replace(
            self.config, databricks_integration_mode="genie-one",
            databricks_workspace_id="123", databricks_genie_space_id="",
        )
        with patch("foundry_databricks_genie.setup.subprocess.run") as run:
            with self.assertRaisesRegex(ConfigurationError, "unverified"):
                setup(self.config, self.output)
            run.assert_not_called()

    def test_managed_replacement_is_explicit_and_verified(self) -> None:
        with contextlib.redirect_stderr(io.StringIO()) as errors:
            run = self.run_setup(
                [self.names, self.toolboxes, self.names, {}, self.connection()],
                replace_connection=True,
            )
        commands = [call.args[0] for call in run.call_args_list]
        self.assertEqual(commands[2][2:5], ["toolbox", "connection", "list"])
        self.assertIn("--force", commands[3])
        self.assertIn("every consumer", errors.getvalue())

    def test_toolbox_mismatch_blocks_replacement_before_any_mutation(self) -> None:
        with self.assertRaisesRegex(ConfigurationError, "does not reference"):
            self.run_setup(
                [self.names, self.toolboxes, [{"name": "other"}]],
                replace_connection=True,
            )
        self.assertFalse(self.output.exists())

    def test_creation_is_not_success_until_connection_and_toolbox_match(self) -> None:
        for documents in (
            [[], [], {}, self.connection(target="https://other.example")],
            [[], [], {}, self.connection(), {}, [{"name": "other"}]],
        ):
            with self.subTest(documents=documents):
                with self.assertRaises(ConfigurationError):
                    self.run_setup(documents)

    def test_cli_failure_is_not_absence_and_does_not_expose_output(self) -> None:
        marker = "sensitive-diagnostic-canary"
        with patch("foundry_databricks_genie.setup.shutil.which", return_value="azd"):
            with patch("foundry_databricks_genie.setup.subprocess.run", return_value=
                       subprocess.CompletedProcess([], 1, marker, marker)) as run:
                with self.assertRaisesRegex(ConfigurationError, "failed") as caught:
                    setup(self.config, self.output)
        self.assertNotIn(marker, str(caught.exception))
        self.assertEqual(run.call_count, 1)
        self.assertFalse(self.output.exists())

    def test_timeout_reports_uncertain_resource_state_without_retry(self) -> None:
        with patch("foundry_databricks_genie.setup.shutil.which", return_value="azd"):
            with patch("foundry_databricks_genie.setup.subprocess.run", side_effect=
                       subprocess.TimeoutExpired("azd", 120)) as run:
                with self.assertRaisesRegex(ConfigurationError, "may have completed"):
                    setup(self.config, self.output)
        self.assertEqual(run.call_count, 1)

    def test_rejects_unknown_or_incomplete_resource_lists(self) -> None:
        for document in (
            {}, {"error": "denied"}, {"value": [], "nextLink": "more"},
            [{"metadata": {"name": "decoy"}}],
            [{"name": "same"}, {"name": "same"}],
        ):
            with self.subTest(document=document):
                with self.assertRaises(ConfigurationError):
                    resource_exists(document, "connections", "target")

    def test_accepts_complete_list_envelopes(self) -> None:
        for document in (self.names, {"value": self.names}, {"connections": self.names}):
            self.assertTrue(resource_exists(document, "connections", "databricks-genie"))
            self.assertFalse(resource_exists(document, "connections", "other"))

    def test_connection_checks_exact_resource_not_nested_decoys(self) -> None:
        for document in (
            {"properties": self.connection()["properties"]},
            {"name": "other", "metadata": self.connection()},
            {"name": "databricks-genie", "metadata": self.connection()},
        ):
            with self.assertRaises(ConfigurationError):
                assert_connection(document, "databricks-genie", self.config.genie_mcp_endpoint)

    def test_genie_one_query_parameter_is_not_normalized_as_a_path(self) -> None:
        endpoint = (
            "https://example.azuredatabricks.net/ai-gateway/mcp-services/"
            "system.ai.genie_one_mcp?o=123"
        )
        for target in (endpoint + "/", endpoint + "&other=1", endpoint.replace("123", "124")):
            with self.subTest(target=target), self.assertRaises(ConfigurationError):
                assert_connection(self.connection(target=target), "databricks-genie", endpoint)
        assert_connection(self.connection(target=endpoint), "databricks-genie", endpoint)

    def test_rejects_non_oauth_or_wrong_category(self) -> None:
        for changes in (
            {"authType": "ApiKey"}, {"authType": None},
            {"authType": "UserEntraToken"}, {"category": "RemoteA2A"},
        ):
            with self.assertRaises(ConfigurationError):
                assert_connection(
                    self.connection(**changes), "databricks-genie",
                    self.config.genie_mcp_endpoint, require_oauth=True,
                )

    def test_scopes_are_validated_when_exposed(self) -> None:
        for scopes in (["genie", "offline_access"], "genie offline_access", "genie,offline_access"):
            assert_connection(
                self.connection(scopes=scopes), "databricks-genie",
                self.config.genie_mcp_endpoint, require_oauth=True,
                required_scopes=("genie", "offline_access"),
            )
        for scopes in (["genie"], ["ai-gateway", "offline_access"], {}, 123):
            with self.assertRaises(ConfigurationError):
                assert_connection(
                    self.connection(scopes=scopes), "databricks-genie",
                    self.config.genie_mcp_endpoint, require_oauth=True,
                    required_scopes=("genie", "offline_access"),
                )

    def test_unexposed_scopes_are_explicitly_unverified(self) -> None:
        with contextlib.redirect_stderr(io.StringIO()) as errors:
            assert_connection(
                self.connection(scopes=None), "databricks-genie",
                self.config.genie_mcp_endpoint, require_oauth=True,
                required_scopes=("genie", "offline_access"),
            )
        self.assertIn("NOT VERIFIED", errors.getvalue())

    def test_toolbox_name_alone_cannot_match_connection(self) -> None:
        with self.assertRaises(ConfigurationError):
            assert_toolbox_connections({
                "name": "databricks-genie", "connections": [{"name": "other"}]
            }, "databricks-genie")

    def test_json_errors_do_not_expose_input(self) -> None:
        with self.assertRaises(ConfigurationError) as caught:
            parse_json("sensitive-diagnostic-canary")
        self.assertNotIn("sensitive-diagnostic-canary", str(caught.exception))

    def test_template_matches_renderer(self) -> None:
        root = Path(__file__).resolve().parents[1]
        template = (root / "config" / "toolbox.yaml.template").read_text()
        self.assertEqual(
            template.replace("${FOUNDRY_CONNECTION_NAME}", "databricks-genie"),
            render_toolbox("databricks-genie"),
        )


if __name__ == "__main__":
    unittest.main()
