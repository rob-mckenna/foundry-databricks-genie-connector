from __future__ import annotations

import json
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
