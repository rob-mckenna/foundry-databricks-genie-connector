"""Load and validate non-secret connector configuration."""

from __future__ import annotations

import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urlparse


class ConfigurationError(ValueError):
    """Raised when connector configuration is missing or invalid."""


_RESOURCE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$")
_SPACE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
_PLACEHOLDER_MARKERS = ("<", ">", "changeme", "replace-me")


@dataclass(frozen=True)
class Configuration:
    foundry_project_endpoint: str
    databricks_workspace_host: str
    databricks_genie_space_id: str
    foundry_connection_name: str
    foundry_toolbox_name: str

    @property
    def genie_mcp_endpoint(self) -> str:
        return (
            f"{self.databricks_workspace_host}/api/2.0/mcp/genie/"
            f"{self.databricks_genie_space_id}"
        )

    def to_dict(self) -> dict[str, str]:
        values = asdict(self)
        values["genie_mcp_endpoint"] = self.genie_mcp_endpoint
        return values


def _read_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        raise ConfigurationError(
            f"Configuration file not found: {path}. Copy .env.example to .env."
        )

    values: dict[str, str] = {}
    for line_number, raw_line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ConfigurationError(
                f"Invalid line {line_number} in {path}: expected NAME=VALUE."
            )
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key] = value
    return values


def _required(values: dict[str, str], key: str) -> str:
    value = values.get(key, "").strip()
    if not value:
        raise ConfigurationError(f"Missing required configuration value: {key}.")
    if any(marker in value.lower() for marker in _PLACEHOLDER_MARKERS):
        raise ConfigurationError(f"Replace the placeholder value for {key}.")
    return value


def _validate_https_url(value: str, key: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ConfigurationError(f"{key} must be a valid HTTPS URL.")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ConfigurationError(
            f"{key} must not contain credentials, a query, or a fragment."
        )
    return value.rstrip("/")


def _validate_resource_name(value: str, key: str) -> str:
    if not _RESOURCE_NAME.fullmatch(value):
        raise ConfigurationError(
            f"{key} must start with an alphanumeric character and contain only "
            "letters, numbers, underscores, or hyphens (maximum 80 characters)."
        )
    return value


def load_configuration(env_file: str | Path = ".env") -> Configuration:
    file_values = _read_env_file(Path(env_file))
    values = {**file_values}
    for key in (
        "FOUNDRY_PROJECT_ENDPOINT",
        "DATABRICKS_WORKSPACE_HOST",
        "DATABRICKS_GENIE_SPACE_ID",
        "FOUNDRY_CONNECTION_NAME",
        "FOUNDRY_TOOLBOX_NAME",
    ):
        if key in os.environ:
            values[key] = os.environ[key]

    project_endpoint = _validate_https_url(
        _required(values, "FOUNDRY_PROJECT_ENDPOINT"),
        "FOUNDRY_PROJECT_ENDPOINT",
    )
    if "/api/projects/" not in urlparse(project_endpoint).path:
        raise ConfigurationError(
            "FOUNDRY_PROJECT_ENDPOINT must contain /api/projects/<project>."
        )

    workspace_host = _validate_https_url(
        _required(values, "DATABRICKS_WORKSPACE_HOST"),
        "DATABRICKS_WORKSPACE_HOST",
    )
    if urlparse(workspace_host).path not in ("", "/"):
        raise ConfigurationError(
            "DATABRICKS_WORKSPACE_HOST must be the workspace root URL."
        )

    space_id = _required(values, "DATABRICKS_GENIE_SPACE_ID")
    if not _SPACE_ID.fullmatch(space_id):
        raise ConfigurationError(
            "DATABRICKS_GENIE_SPACE_ID contains unsupported characters."
        )

    return Configuration(
        foundry_project_endpoint=project_endpoint,
        databricks_workspace_host=workspace_host,
        databricks_genie_space_id=space_id,
        foundry_connection_name=_validate_resource_name(
            _required(values, "FOUNDRY_CONNECTION_NAME"),
            "FOUNDRY_CONNECTION_NAME",
        ),
        foundry_toolbox_name=_validate_resource_name(
            _required(values, "FOUNDRY_TOOLBOX_NAME"),
            "FOUNDRY_TOOLBOX_NAME",
        ),
    )

