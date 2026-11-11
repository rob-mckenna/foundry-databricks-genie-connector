from __future__ import annotations

import json
import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from foundry_databricks_genie.cli import main
from foundry_databricks_genie.config import (
    ConfigurationError,
    load_configuration,
)


VALID_ENV = """\
FOUNDRY_PROJECT_ENDPOINT=https://example.services.ai.azure.com/api/projects/demo
DATABRICKS_WORKSPACE_HOST=https://example.azuredatabricks.net/
DATABRICKS_GENIE_SPACE_ID=space_123-abc
FOUNDRY_CONNECTION_NAME=databricks-genie
FOUNDRY_TOOLBOX_NAME=databricks-genie-toolbox
"""


class ConfigurationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_directory.cleanup)
        self.env_file = Path(self.temp_directory.name) / ".env"
        self.env_file.write_text(VALID_ENV, encoding="utf-8")

    def test_loads_valid_configuration_and_builds_endpoint(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            configuration = load_configuration(self.env_file)

        self.assertEqual(
            configuration.genie_mcp_endpoint,
            "https://example.azuredatabricks.net/api/2.0/mcp/genie/"
            "space_123-abc",
        )

    def test_environment_overrides_file_value(self) -> None:
        with patch.dict(
            os.environ,
            {"DATABRICKS_GENIE_SPACE_ID": "environment-space"},
            clear=True,
        ):
            configuration = load_configuration(self.env_file)

        self.assertEqual(configuration.databricks_genie_space_id, "environment-space")

    def test_legacy_defaults_preserve_public_fields_and_endpoint(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            configuration = load_configuration(self.env_file)
        self.assertEqual(configuration.databricks_integration_mode, "genie-agent")
        self.assertEqual(configuration.foundry_connection_mode, "managed-oauth")
        self.assertEqual(configuration.required_oauth_scopes, ("genie", "offline_access"))
        self.assertEqual(
            configuration.toolbox_mcp_endpoint,
            "https://example.services.ai.azure.com/api/projects/demo/"
            "toolboxes/databricks-genie-toolbox/mcp?api-version=v1",
        )

    def test_genie_one_endpoint_includes_exact_service_and_workspace_query(self) -> None:
        self.env_file.write_text(
            VALID_ENV.replace("DATABRICKS_GENIE_SPACE_ID=space_123-abc\n", "")
            + "DATABRICKS_INTEGRATION_MODE=genie-one\n"
            + "DATABRICKS_WORKSPACE_ID=1234567890123456\n"
            + "FOUNDRY_CONNECTION_MODE=existing-oauth\n",
            encoding="utf-8",
        )
        with patch.dict(os.environ, {}, clear=True):
            configuration = load_configuration(self.env_file)
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                result = main(["endpoint", "--env-file", str(self.env_file)])
        expected = (
            "https://example.azuredatabricks.net/ai-gateway/mcp-services/"
            "system.ai.genie_one_mcp?o=1234567890123456"
        )
        self.assertEqual(configuration.genie_mcp_endpoint, expected)
        self.assertEqual(configuration.required_oauth_scopes, ("ai-gateway", "offline_access"))
        self.assertEqual(configuration.databricks_genie_space_id, "")
        self.assertEqual(output.getvalue().strip(), expected)
        self.assertEqual(result, 0)

    def test_new_environment_settings_override_file(self) -> None:
        with patch.dict(os.environ, {
            "DATABRICKS_INTEGRATION_MODE": "genie-one",
            "DATABRICKS_WORKSPACE_ID": "123",
            "DATABRICKS_GENIE_SPACE_ID": "",
            "FOUNDRY_CONNECTION_MODE": "existing-oauth",
        }, clear=True):
            configuration = load_configuration(self.env_file)
        self.assertTrue(configuration.genie_mcp_endpoint.endswith("?o=123"))

    def test_rejects_invalid_modes_and_conditional_parameters(self) -> None:
        cases = [
            ({"DATABRICKS_INTEGRATION_MODE": "other"}, "INTEGRATION_MODE"),
            ({"DATABRICKS_INTEGRATION_MODE": ""}, "INTEGRATION_MODE"),
            ({"FOUNDRY_CONNECTION_MODE": "pat"}, "CONNECTION_MODE"),
            ({"DATABRICKS_GENIE_SPACE_ID": ""}, "GENIE_SPACE_ID"),
            ({"DATABRICKS_WORKSPACE_ID": "123"}, "unused"),
            ({"DATABRICKS_INTEGRATION_MODE": "genie-one"}, "WORKSPACE_ID"),
        ]
        one = {
            "DATABRICKS_INTEGRATION_MODE": "genie-one",
            "DATABRICKS_GENIE_SPACE_ID": "",
            "DATABRICKS_WORKSPACE_ID": "123",
            "FOUNDRY_CONNECTION_MODE": "existing-oauth",
        }
        for value in ("0", "-1", "1.5", "12&other=1", "<workspace-id>", "abc"):
            cases.append(({**one, "DATABRICKS_WORKSPACE_ID": value}, "WORKSPACE_ID"))
        cases.extend([
            ({**one, "DATABRICKS_GENIE_SPACE_ID": "old-space"}, "not scoped"),
            ({**one, "FOUNDRY_CONNECTION_MODE": "managed-oauth"}, "unverified"),
        ])
        for overrides, message in cases:
            with self.subTest(overrides=overrides):
                with patch.dict(os.environ, overrides, clear=True):
                    with self.assertRaisesRegex(ConfigurationError, message):
                        load_configuration(self.env_file)

    def test_rejects_unsafe_workspace_urls_without_echoing_value(self) -> None:
        for host in (
            "http://example.azuredatabricks.net",
            "https://user:password@example.azuredatabricks.net",
            "https://example.azuredatabricks.net?token=sensitive",
            "https://example.azuredatabricks.net#fragment",
            "https://example.azuredatabricks.net:invalid",
            "https://example.azuredatabricks.net:99999",
            "https://example.azuredatabricks.net\\other",
            "https://example.azure\tdatabricks.net",
            "https://[invalid",
        ):
            with self.subTest(host=host), patch.dict(
                os.environ, {"DATABRICKS_WORKSPACE_HOST": host}, clear=True
            ):
                with self.assertRaises(ConfigurationError) as caught:
                    load_configuration(self.env_file)
                self.assertNotIn(host, str(caught.exception))

    def test_rejects_empty_or_nested_project_name(self) -> None:
        for path in ("/api/projects/", "/api/projects/demo/other", "/other/api/projects/demo"):
            with patch.dict(os.environ, {
                "FOUNDRY_PROJECT_ENDPOINT": "https://example.services.ai.azure.com" + path
            }, clear=True):
                with self.assertRaises(ConfigurationError):
                    load_configuration(self.env_file)

    def test_missing_file_and_malformed_file_are_explicit_errors(self) -> None:
        with self.assertRaisesRegex(ConfigurationError, "not found"):
            load_configuration(self.env_file.with_name("missing.env"))
        self.env_file.write_text("invalid line", encoding="utf-8")
        with self.assertRaisesRegex(ConfigurationError, "expected NAME=VALUE"):
            load_configuration(self.env_file)

    def test_utf8_bom_configuration_and_json_are_supported(self) -> None:
        self.env_file.write_text(VALID_ENV, encoding="utf-8-sig")
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(load_configuration(self.env_file).foundry_connection_name, "databricks-genie")
        state = Path(self.temp_directory.name) / "toolbox.json"
        state.write_text('{"connections":[{"name":"databricks-genie"}]}', encoding="utf-8-sig")
        self.assertEqual(main([
            "assert-toolbox-connections", "--input", str(state),
            "--expected-name", "databricks-genie",
        ]), 0)

    def test_rejects_placeholder_values(self) -> None:
        self.env_file.write_text(
            VALID_ENV.replace("space_123-abc", "<genie-space-id>"),
            encoding="utf-8",
        )
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ConfigurationError, "placeholder"):
                load_configuration(self.env_file)

    def test_rejects_workspace_path(self) -> None:
        self.env_file.write_text(
            VALID_ENV.replace(
                "https://example.azuredatabricks.net/",
                "https://example.azuredatabricks.net/not-the-root",
            ),
            encoding="utf-8",
        )
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ConfigurationError, "workspace root"):
                load_configuration(self.env_file)

    def test_rejects_project_endpoint_without_project_path(self) -> None:
        self.env_file.write_text(
            VALID_ENV.replace(
                "https://example.services.ai.azure.com/api/projects/demo",
                "https://example.services.ai.azure.com/",
            ),
            encoding="utf-8",
        )
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ConfigurationError, "/api/projects/"):
                load_configuration(self.env_file)

    def test_rendered_toolbox_contains_only_connection_reference(self) -> None:
        output = Path(self.temp_directory.name) / "generated" / "toolbox.yaml"
        with patch.dict(os.environ, {}, clear=True):
            result = main(
                [
                    "render-toolbox",
                    "--env-file",
                    str(self.env_file),
                    "--output",
                    str(output),
                ]
            )

        self.assertEqual(result, 0)
        self.assertEqual(
            output.read_text(encoding="utf-8"),
            "description: Azure Databricks Genie tools exposed through a managed "
            "Foundry Toolbox.\n"
            "connections:\n"
            "  - name: databricks-genie\n",
        )

    def test_config_json_has_no_secret_fields(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            configuration = load_configuration(self.env_file)
        serialized = json.dumps(configuration.to_dict()).lower()
        for forbidden in ("secret", "password", "bearer", "token"):
            self.assertNotIn(forbidden, serialized)

    def test_asserts_matching_existing_connection(self) -> None:
        state = Path(self.temp_directory.name) / "connection.json"
        state.write_text(
            json.dumps(
                {
                    "name": "databricks-genie",
                    "properties": {
                        "target": (
                            "https://example.azuredatabricks.net/api/2.0/mcp/"
                            "genie/space_123-abc"
                        )
                    },
                }
            ),
            encoding="utf-8",
        )
        result = main(
            [
                "assert-connection",
                "--input",
                str(state),
                "--expected-name",
                "databricks-genie",
                "--expected-target",
                (
                    "https://example.azuredatabricks.net/api/2.0/mcp/"
                    "genie/space_123-abc"
                ),
            ]
        )
        self.assertEqual(result, 0)

    def test_rejects_existing_connection_with_different_target(self) -> None:
        state = Path(self.temp_directory.name) / "connection.json"
        state.write_text(
            json.dumps(
                {
                    "name": "databricks-genie",
                    "target": "https://other.example/api/2.0/mcp/genie/other",
                }
            ),
            encoding="utf-8",
        )
        result = main(
            [
                "assert-connection",
                "--input",
                str(state),
                "--expected-name",
                "databricks-genie",
                "--expected-target",
                (
                    "https://example.azuredatabricks.net/api/2.0/mcp/"
                    "genie/space_123-abc"
                ),
            ]
        )
        self.assertEqual(result, 2)

    def test_rejects_toolbox_without_expected_connection(self) -> None:
        state = Path(self.temp_directory.name) / "toolbox.json"
        state.write_text(
            json.dumps({"connections": [{"name": "different-connection"}]}),
            encoding="utf-8",
        )
        result = main(
            [
                "assert-toolbox-connections",
                "--input",
                str(state),
                "--expected-name",
                "databricks-genie",
            ]
        )
        self.assertEqual(result, 2)


if __name__ == "__main__":
    unittest.main()
