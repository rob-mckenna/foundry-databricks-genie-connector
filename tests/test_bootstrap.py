from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import time
import unittest
import warnings
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock, patch

from foundry_databricks_genie.bootstrap import (
    OWNER, _assert_active_routing, _assert_agent, _definition, _ensure_binding, _metadata,
    _toolbox_endpoint, execute_bootstrap, provision_agent,
)
from foundry_databricks_genie.cli import main
from foundry_databricks_genie.config import (
    BootstrapConfiguration, Configuration, ConfigurationError, load_bootstrap_configuration,
)

try:
    from azure.ai.projects.models import MCPTool, PromptAgentDefinition
    from azure.core.exceptions import HttpResponseError, ResourceNotFoundError
    SDK_AVAILABLE = True
except ImportError:
    SDK_AVAILABLE = False


CONFIG = Configuration(
    "https://example.services.ai.azure.com/api/projects/demo",
    "https://example.azuredatabricks.net", "space_123-abc", "genie", "genie-toolbox",
)
SETTINGS = BootstrapConfiguration("genie-test", "existing-model", "genie-test-toolbox")
ENDPOINT = CONFIG.foundry_project_endpoint + "/toolboxes/genie-toolbox/versions/2/mcp?api-version=v1"
ENV = """\
FOUNDRY_PROJECT_ENDPOINT=https://example.services.ai.azure.com/api/projects/demo
DATABRICKS_WORKSPACE_HOST=https://example.azuredatabricks.net
DATABRICKS_GENIE_SPACE_ID=space_123-abc
FOUNDRY_CONNECTION_NAME=genie
FOUNDRY_TOOLBOX_NAME=genie-toolbox
FOUNDRY_TEST_AGENT_NAME=genie-test
FOUNDRY_MODEL_DEPLOYMENT=existing-model
"""


def agent() -> dict[str, object]:
    return {
        "name": SETTINGS.agent_name, "version": "7", "status": "active",
        "metadata": _metadata(CONFIG), "definition": _definition(SETTINGS, ENDPOINT),
    }


class BootstrapConfigurationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.env = Path(self.directory.name) / "test.env"
        self.env.write_text(ENV, encoding="utf-8")
        self.environment = patch.dict(os.environ, {}, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def test_bootstrap_defaults_and_environment_overrides(self) -> None:
        self.assertEqual(load_bootstrap_configuration(self.env, CONFIG), SETTINGS)
        with patch.dict(os.environ, {"FOUNDRY_TEST_AGENT_NAME": "different"}):
            self.assertEqual(
                load_bootstrap_configuration(self.env, CONFIG).toolbox_connection_name,
                "different-toolbox",
            )
        with patch.dict(os.environ, {"FOUNDRY_MODEL_DEPLOYMENT": "gpt-4.1"}):
            self.assertEqual(
                load_bootstrap_configuration(self.env, CONFIG).model_deployment, "gpt-4.1"
            )

    def test_missing_model_name_and_connection_collision_rejected(self) -> None:
        for overrides in (
            {"FOUNDRY_MODEL_DEPLOYMENT": ""},
            {"FOUNDRY_TEST_AGENT_NAME": "<agent>"},
            {"FOUNDRY_TOOLBOX_CONNECTION_NAME": CONFIG.foundry_connection_name},
            {"FOUNDRY_MODEL_DEPLOYMENT": "model/invalid"},
        ):
            with patch.dict(os.environ, overrides), self.assertRaises(ConfigurationError):
                load_bootstrap_configuration(self.env, CONFIG)

    def test_bootstrap_does_not_send_platform_tokens_to_custom_hosts(self) -> None:
        for endpoint in (
            "https://other.example/api/projects/demo",
            "https://example.services.ai.azure.com.other.example/api/projects/demo",
            "https://example.services.ai.azure.com:8443/api/projects/demo",
        ):
            with self.subTest(endpoint=endpoint), self.assertRaises(ConfigurationError):
                load_bootstrap_configuration(
                    self.env, replace(CONFIG, foundry_project_endpoint=endpoint)
                )

    def test_plan_never_imports_sdk_executes_cloud_or_writes_files(self) -> None:
        output_file = Path(self.directory.name) / "generated" / "toolbox.yaml"
        with patch("foundry_databricks_genie.bootstrap.execute_bootstrap") as execute:
            with contextlib.redirect_stdout(io.StringIO()) as output:
                result = main([
                    "bootstrap", "--env-file", str(self.env), "--output", str(output_file),
                ])
        self.assertEqual(result, 0)
        self.assertIn("PLAN ONLY", output.getvalue())
        execute.assert_not_called()
        self.assertFalse(output_file.exists())

    def test_explicit_apply_wires_smoke_options_without_printing_question(self) -> None:
        question = Path(self.directory.name) / "question.txt"
        question.write_text("synthetic-private-question", encoding="utf-8")
        with patch("foundry_databricks_genie.bootstrap.execute_bootstrap", return_value=3) as execute:
            with contextlib.redirect_stdout(io.StringIO()) as output:
                result = main([
                    "bootstrap", "--env-file", str(self.env), "--apply",
                    "--question-file", str(question), "--approve-tools", "--non-interactive",
                ])
        self.assertEqual(result, 3)
        self.assertEqual(execute.call_args.args[3], "synthetic-private-question")
        self.assertTrue(execute.call_args.kwargs["approve_tools"])
        self.assertTrue(execute.call_args.kwargs["non_interactive"])
        self.assertNotIn("synthetic-private-question", output.getvalue())

    def test_approval_without_question_fails_before_cloud_access(self) -> None:
        with patch("foundry_databricks_genie.bootstrap.execute_bootstrap") as execute:
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main([
                    "bootstrap", "--env-file", str(self.env), "--apply", "--approve-tools"
                ]), 2)
        execute.assert_not_called()


class BootstrapShapeTests(unittest.TestCase):
    def test_active_endpoint_routing_must_match_verified_version(self) -> None:
        for selected in ("7", "@latest"):
            document = {
                "state": "enabled", "versions": {"latest": {"version": "7"}},
                "agent_endpoint": {"version_selector": {"version_selection_rules": [
                    {"type": "FixedRatio", "agent_version": selected, "traffic_percentage": 100}
                ]}},
            }
            _assert_active_routing(document, "7")
            with self.assertRaises(ConfigurationError):
                _assert_active_routing(document, "8")
        for selected, percentage in (("latest", 100), ("@latest", 50)):
            document = {
                "state": "enabled", "versions": {"latest": {"version": "7"}},
                "agent_endpoint": {"version_selector": {"version_selection_rules": [
                    {"type": "FixedRatio", "agent_version": selected, "traffic_percentage": percentage}
                ]}},
            }
            with self.assertRaises(ConfigurationError):
                _assert_active_routing(document, "7")
        with self.assertRaises(ConfigurationError):
            _assert_active_routing({"state": "enabled"}, "7")

    def test_agent_has_only_pinned_toolbox_and_keeps_approval_enabled(self) -> None:
        self.assertEqual(_assert_agent(agent(), CONFIG, SETTINGS, ENDPOINT), "7")
        definition = _definition(SETTINGS, ENDPOINT)
        self.assertEqual(definition["tools"], [{
            "type": "mcp", "server_label": "genie_toolbox", "server_url": ENDPOINT,
            "project_connection_id": SETTINGS.toolbox_connection_name,
            "require_approval": "always",
        }])

    def test_unowned_changed_or_inactive_agents_are_rejected(self) -> None:
        for changes in (
            {"metadata": {}}, {"status": "failed"}, {"name": "other"},
            {"version": None},
            {"definition": {**_definition(SETTINGS, ENDPOINT), "tools": []}},
            {"definition": {**_definition(SETTINGS, ENDPOINT), "model": "other"}},
            {"definition": {**_definition(SETTINGS, ENDPOINT), "skills": [{"name": "other"}]}},
        ):
            with self.subTest(changes=changes), self.assertRaises(ConfigurationError):
                _assert_agent({**agent(), **changes}, CONFIG, SETTINGS, ENDPOINT)

    def test_toolbox_must_contain_only_expected_connection(self) -> None:
        project = Mock()
        project.toolboxes.get.return_value.default_version = "2"
        tool = {"type": "mcp", "project_connection_id": "genie"}
        project.toolboxes.get_version.return_value.as_dict.return_value = {"tools": [tool]}
        self.assertEqual(_toolbox_endpoint(project, CONFIG), ENDPOINT)
        for document in (
            {"tools": []}, {"tools": [tool, tool]}, {"tools": [tool], "skills": [{"name": "other"}]},
            {"tools": [{"type": "mcp", "project_connection_id": "other"}]},
            {"tools": [{**tool, "server_url": "https://other.example"}]},
            {"tools": [{**tool, "headers": {"Authorization": "redacted"}}]},
        ):
            project.toolboxes.get_version.return_value.as_dict.return_value = document
            with self.assertRaises(ConfigurationError):
                _toolbox_endpoint(project, CONFIG)

    def test_binding_creation_and_verification(self) -> None:
        binding = {
            "name": SETTINGS.toolbox_connection_name,
            "properties": {"target": ENDPOINT, "authType": "UserEntraToken", "audience": "https://ai.azure.com"},
        }
        with patch("foundry_databricks_genie.bootstrap._run_azd", side_effect=[
            "[]", "{}", json.dumps(binding),
        ]) as run:
            _ensure_binding(CONFIG, SETTINGS, ENDPOINT)
        arguments = run.call_args_list[1].args
        self.assertIn("user-entra-token", arguments)
        self.assertIn("https://ai.azure.com", arguments)
        self.assertNotIn("--force", arguments)

    def test_toolbox_accepts_authoritative_connection_id_but_not_cross_project_id(self) -> None:
        connection_id = "/projects/current/connections/genie"
        project = Mock()
        project.toolboxes.get.return_value.default_version = "2"
        project.connections.get.return_value.id = connection_id
        project.toolboxes.get_version.return_value.as_dict.return_value = {
            "tools": [{"type": "mcp", "project_connection_id": connection_id}],
        }
        self.assertEqual(_toolbox_endpoint(project, CONFIG), ENDPOINT)
        project.connections.get.assert_called_once_with("genie", include_credentials=False)
        project.toolboxes.get_version.return_value.as_dict.return_value = {
            "tools": [{"type": "mcp", "project_connection_id": "/projects/other/connections/genie"}],
        }
        with self.assertRaisesRegex(ConfigurationError, "another project"):
            _toolbox_endpoint(project, CONFIG)

    def test_wrong_binding_never_replaced(self) -> None:
        for changes in (
            {"authType": "OAuth2"}, {"audience": "https://other.example"},
            {"target": "https://other.example"},
        ):
            binding = {
                "name": SETTINGS.toolbox_connection_name,
                "properties": {"target": ENDPOINT, "authType": "UserEntraToken",
                               "audience": "https://ai.azure.com", **changes},
            }
            with patch("foundry_databricks_genie.bootstrap._run_azd", side_effect=[
                json.dumps([{"name": SETTINGS.toolbox_connection_name}]), json.dumps(binding),
            ]) as run:
                with self.assertRaises(ConfigurationError):
                    _ensure_binding(CONFIG, SETTINGS, ENDPOINT)
                self.assertEqual(run.call_count, 2)

    def test_binding_audience_uses_non_secret_arm_metadata_when_omitted(self) -> None:
        projection = {
            "name": SETTINGS.toolbox_connection_name, "target": ENDPOINT,
            "authType": "UserEntraToken",
        }
        project = Mock()
        project.connections.get.return_value.id = (
            "/subscriptions/example/resourceGroups/demo/providers/"
            "Microsoft.CognitiveServices/accounts/foundry/projects/demo/"
            "connections/genie-test-toolbox"
        )
        arm = Mock()
        arm.send_request.return_value.status_code = 200
        arm.send_request.return_value.text.return_value = json.dumps({
            "name": SETTINGS.toolbox_connection_name,
            "properties": {
                "target": ENDPOINT, "authType": "UserEntraToken",
                "audience": "https://ai.azure.com",
            },
        })
        with patch("foundry_databricks_genie.bootstrap._run_azd", side_effect=[
            json.dumps([{"name": SETTINGS.toolbox_connection_name}]), json.dumps(projection),
        ]):
            _ensure_binding(CONFIG, SETTINGS, ENDPOINT, project=project, arm=arm)
        project.connections.get.assert_called_once_with(
            SETTINGS.toolbox_connection_name, include_credentials=False
        )
        self.assertIn("api-version=2025-09-01", arm.get.call_args.args[0])

    def test_arm_audience_verification_fails_closed(self) -> None:
        projection = {
            "name": SETTINGS.toolbox_connection_name, "target": ENDPOINT,
            "authType": "UserEntraToken",
        }
        project = Mock()
        project.connections.get.return_value.id = "/subscriptions/example/connections/test"
        for status, audience in ((403, "https://ai.azure.com"), (200, "https://other.example")):
            arm = Mock()
            arm.send_request.return_value.status_code = status
            arm.send_request.return_value.text.return_value = json.dumps({
                "name": SETTINGS.toolbox_connection_name,
                "properties": {
                    "target": ENDPOINT, "authType": "UserEntraToken", "audience": audience,
                },
            })
            with patch("foundry_databricks_genie.bootstrap._run_azd", side_effect=[
                json.dumps([{"name": SETTINGS.toolbox_connection_name}]), json.dumps(projection),
            ]):
                with self.assertRaises(ConfigurationError):
                    _ensure_binding(CONFIG, SETTINGS, ENDPOINT, project=project, arm=arm)


@unittest.skipUnless(SDK_AVAILABLE, "Install the bootstrap extra for SDK contract tests.")
class BootstrapSdkTests(unittest.TestCase):
    def test_real_sdk_agent_endpoint_and_oauth_extension_without_network(self) -> None:
        import importlib
        from azure.ai.projects import AIProjectClient
        from azure.core.credentials import AccessToken
        from openai import DefaultHttpxClient
        from foundry_databricks_genie.smoke import run_smoke
        from test_smoke import answer, call

        transport_module = next(
            base.__module__.split(".")[0] for base in DefaultHttpxClient.__mro__
            if base.__module__.split(".")[0] in ("httpx", "httpx2")
        )
        http = importlib.import_module(transport_module)
        requests = []
        documents = [
            {"id": "response_1", "status": "incomplete", "output": [{
                "type": "oauth_consent_request",
                "consent_link": "https://login.example/authorize?code=private-canary",
            }]},
            {"id": "response_2", "status": "completed", "output": [call(), answer()]},
        ]

        def respond(request):
            requests.append(request)
            return http.Response(200, json={
                "object": "response", "created_at": 0, "model": "existing-model",
                **documents[len(requests) - 1],
            })

        credential = Mock(spec=["get_token"])
        credential.get_token.return_value = AccessToken("offline-test", int(time.time()) + 3600)
        with AIProjectClient(
            endpoint=CONFIG.foundry_project_endpoint, credential=credential, allow_preview=True
        ) as project:
            with project.get_openai_client(
                agent_name=SETTINGS.agent_name, max_retries=0,
                http_client=http.Client(transport=http.MockTransport(respond)),
            ) as client:
                with patch("foundry_databricks_genie.smoke._consent", return_value=True):
                    with warnings.catch_warnings(record=True) as captured:
                        with contextlib.redirect_stdout(io.StringIO()) as output:
                            result = run_smoke(client, "genie-agent", "synthetic-question")
        self.assertEqual(result, 0)
        self.assertEqual(len(requests), 2)
        self.assertTrue(requests[0].url.path.endswith(
            "/agents/genie-test/endpoint/protocols/openai/responses"
        ))
        self.assertNotIn("agent_reference", json.loads(requests[0].content))
        self.assertNotIn("previous_response_id", json.loads(requests[0].content))
        self.assertEqual(json.loads(requests[1].content)["previous_response_id"], "response_1")
        self.assertNotIn("private-canary", output.getvalue())
        self.assertFalse(any("private-canary" in str(item.message) for item in captured))

    def test_definition_serializes_with_supported_sdk_models(self) -> None:
        definition = _definition(SETTINGS, ENDPOINT)
        typed = PromptAgentDefinition(definition)
        self.assertEqual(typed.as_dict(), definition)
        self.assertIsInstance(typed.tools[0], MCPTool)

    def test_unrelated_agent_and_failed_model_lookup_prevent_mutations(self) -> None:
        project = Mock()
        project.agents.get.return_value.state = "enabled"
        project.agents.get.return_value.versions.latest.as_dict.return_value = {
            **agent(), "metadata": {"created-by": "someone-else"},
        }
        with patch("foundry_databricks_genie.bootstrap.setup") as setup:
            with self.assertRaises(ConfigurationError):
                provision_agent(project, CONFIG, SETTINGS, Path("unused"))
            setup.assert_not_called()
            project.agents.create_version.assert_not_called()
        project.deployments.get.side_effect = HttpResponseError("private-error-canary")
        with patch("foundry_databricks_genie.bootstrap.setup") as setup:
            with self.assertRaises(HttpResponseError):
                provision_agent(project, CONFIG, SETTINGS, Path("unused"))
            setup.assert_not_called()

    def test_missing_agent_is_created_and_persisted_version_checked(self) -> None:
        project = Mock()
        project.agents.get.side_effect = ResourceNotFoundError("missing")
        project.agents.create_version.return_value.version = "7"
        project.agents.get_version.return_value.as_dict.return_value = agent()
        with patch("foundry_databricks_genie.bootstrap.setup") as setup:
            with patch("foundry_databricks_genie.bootstrap._toolbox_endpoint", return_value=ENDPOINT):
                with patch("foundry_databricks_genie.bootstrap._ensure_binding") as binding:
                    self.assertEqual(provision_agent(project, CONFIG, SETTINGS, Path("unused")), "7")
        setup.assert_called_once()
        binding.assert_called_once()
        body = project.agents.create_version.call_args.kwargs["body"]
        self.assertEqual(body["metadata"]["created-by"], OWNER)
        project.agents.get_version.assert_called_once_with(SETTINGS.agent_name, "7")

    def test_matching_agent_is_reused_without_new_version(self) -> None:
        project = Mock()
        project.agents.get.return_value.state = "enabled"
        project.agents.get.return_value.versions.latest.as_dict.return_value = agent()
        with patch("foundry_databricks_genie.bootstrap.setup"):
            with patch("foundry_databricks_genie.bootstrap._toolbox_endpoint", return_value=ENDPOINT):
                with patch("foundry_databricks_genie.bootstrap._ensure_binding"):
                    self.assertEqual(provision_agent(project, CONFIG, SETTINGS, Path("unused")), "7")
        project.agents.create_version.assert_not_called()

    def test_http_errors_are_reported_without_payloads(self) -> None:
        with patch("azure.identity.AzureDeveloperCliCredential"):
            with patch("azure.ai.projects.AIProjectClient"):
                with patch("foundry_databricks_genie.bootstrap.preflight"):
                    with patch("foundry_databricks_genie.bootstrap.provision_agent",
                               side_effect=HttpResponseError("private-error-canary")):
                        with self.assertRaises(ConfigurationError) as caught:
                            execute_bootstrap(CONFIG, SETTINGS, Path("unused"), None)
        self.assertNotIn("private-error-canary", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
