"""Load and validate non-secret connector configuration."""

from __future__ import annotations

import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse


class ConfigurationError(ValueError):
    """Raised when connector configuration is missing or invalid."""


_RESOURCE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$")
_SPACE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
_WORKSPACE_ID = re.compile(r"^[1-9][0-9]*$")
_PLACEHOLDER_MARKERS = ("<", ">", "changeme", "replace-me")


@dataclass(frozen=True)
class Configuration:
    foundry_project_endpoint: str
    databricks_workspace_host: str
    databricks_genie_space_id: str
    foundry_connection_name: str
    foundry_toolbox_name: str
    databricks_integration_mode: Literal["genie-agent", "genie-one"] = "genie-agent"
    databricks_workspace_id: str = ""
    foundry_connection_mode: Literal["managed-oauth", "existing-oauth"] = "managed-oauth"

    @property
    def genie_mcp_endpoint(self) -> str:
        if self.databricks_integration_mode == "genie-one":
            return (
                f"{self.databricks_workspace_host}/ai-gateway/mcp-services/"
                f"system.ai.genie_one_mcp?o={self.databricks_workspace_id}"
            )
        return (
            f"{self.databricks_workspace_host}/api/2.0/mcp/genie/"
            f"{self.databricks_genie_space_id}"
        )

    @property
    def required_oauth_scopes(self) -> tuple[str, str]:
        api_scope = (
            "ai-gateway" if self.databricks_integration_mode == "genie-one" else "genie"
        )
        return api_scope, "offline_access"

    @property
    def toolbox_mcp_endpoint(self) -> str:
        return (
            f"{self.foundry_project_endpoint}/toolboxes/"
            f"{self.foundry_toolbox_name}/mcp?api-version=v1"
        )

    def to_dict(self) -> dict[str, str]:
        values = asdict(self)
        values["genie_mcp_endpoint"] = self.genie_mcp_endpoint
        values["required_oauth_scopes"] = " ".join(self.required_oauth_scopes)
        values["toolbox_mcp_endpoint"] = self.toolbox_mcp_endpoint
        return values


@dataclass(frozen=True)
class BootstrapConfiguration:
    agent_name: str
    model_deployment: str
    toolbox_connection_name: str


def _read_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        raise ConfigurationError(
            f"Configuration file not found: {path}. Copy .env.example to .env."
        )

    values: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except (OSError, UnicodeError) as error:
        raise ConfigurationError("Could not read the configuration file.") from error
    for line_number, raw_line in enumerate(lines, start=1):
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
    if any(character.isspace() or ord(character) < 32 for character in value):
        raise ConfigurationError(f"{key} must not contain whitespace or controls.")
    try:
        parsed = urlparse(value)
        port = parsed.port
    except ValueError as error:
        raise ConfigurationError(f"{key} must be a valid HTTPS URL.") from error
    if parsed.scheme != "https" or not parsed.hostname:
        raise ConfigurationError(f"{key} must be a valid HTTPS URL.")
    if (
        parsed.username is not None
        or parsed.password is not None
        or "?" in value
        or "#" in value
        or "\\" in value
        or port == 0
    ):
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


def _environment_values(env_file: str | Path, keys: tuple[str, ...]) -> dict[str, str]:
    values = _read_env_file(Path(env_file))
    for key in keys:
        if key in os.environ:
            values[key] = os.environ[key]
    return values


def validate_foundry_project(configuration: Configuration) -> None:
    project = urlparse(configuration.foundry_project_endpoint)
    if (
        not project.hostname
        or not re.fullmatch(r"[a-z0-9-]+\.services\.ai\.azure\.com", project.hostname)
        or project.port not in (None, 443)
    ):
        raise ConfigurationError(
            "Agent operations require a public-Azure *.services.ai.azure.com project "
            "hostname (private DNS is supported). It will not send Foundry tokens "
            "to custom hosts or other clouds."
        )


def load_test_agent_name(env_file: str | Path, configuration: Configuration) -> str:
    validate_foundry_project(configuration)
    values = _environment_values(env_file, ("FOUNDRY_TEST_AGENT_NAME",))
    return _validate_resource_name(
        _required(values, "FOUNDRY_TEST_AGENT_NAME"), "FOUNDRY_TEST_AGENT_NAME"
    )


def load_bootstrap_configuration(
    env_file: str | Path, configuration: Configuration
) -> BootstrapConfiguration:
    validate_foundry_project(configuration)
    values = _environment_values(env_file, (
        "FOUNDRY_TEST_AGENT_NAME",
        "FOUNDRY_MODEL_DEPLOYMENT",
        "FOUNDRY_TOOLBOX_CONNECTION_NAME",
    ))
    agent_name = _validate_resource_name(
        _required(values, "FOUNDRY_TEST_AGENT_NAME"), "FOUNDRY_TEST_AGENT_NAME"
    )
    model = _required(values, "FOUNDRY_MODEL_DEPLOYMENT")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", model):
        raise ConfigurationError(
            "FOUNDRY_MODEL_DEPLOYMENT must be a deployment name containing "
            "letters, numbers, underscores, hyphens or periods."
        )
    values.setdefault("FOUNDRY_TOOLBOX_CONNECTION_NAME", f"{agent_name}-toolbox")
    connection = _validate_resource_name(
        _required(values, "FOUNDRY_TOOLBOX_CONNECTION_NAME"),
        "FOUNDRY_TOOLBOX_CONNECTION_NAME",
    )
    if connection == configuration.foundry_connection_name:
        raise ConfigurationError(
            "The agent-to-Toolbox connection must have a different name from "
            "the Databricks OAuth connection."
        )
    return BootstrapConfiguration(agent_name, model, connection)


def load_configuration(env_file: str | Path = ".env") -> Configuration:
    values = _environment_values(env_file, (
        "FOUNDRY_PROJECT_ENDPOINT",
        "DATABRICKS_WORKSPACE_HOST",
        "DATABRICKS_GENIE_SPACE_ID",
        "FOUNDRY_CONNECTION_NAME",
        "FOUNDRY_TOOLBOX_NAME",
        "DATABRICKS_INTEGRATION_MODE",
        "DATABRICKS_WORKSPACE_ID",
        "FOUNDRY_CONNECTION_MODE",
    ))

    project_endpoint = _validate_https_url(
        _required(values, "FOUNDRY_PROJECT_ENDPOINT"),
        "FOUNDRY_PROJECT_ENDPOINT",
    )
    if not re.fullmatch(r"/api/projects/[^/]+", urlparse(project_endpoint).path):
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

    mode = values.get("DATABRICKS_INTEGRATION_MODE", "genie-agent").strip()
    if mode not in ("genie-agent", "genie-one"):
        raise ConfigurationError(
            "DATABRICKS_INTEGRATION_MODE must be genie-agent or genie-one."
        )
    connection_mode = values.get("FOUNDRY_CONNECTION_MODE", "managed-oauth").strip()
    if connection_mode not in ("managed-oauth", "existing-oauth"):
        raise ConfigurationError(
            "FOUNDRY_CONNECTION_MODE must be managed-oauth or existing-oauth."
        )
    space_id = values.get("DATABRICKS_GENIE_SPACE_ID", "").strip()
    workspace_id = values.get("DATABRICKS_WORKSPACE_ID", "").strip()
    if mode == "genie-agent":
        space_id = _required(values, "DATABRICKS_GENIE_SPACE_ID")
        if not _SPACE_ID.fullmatch(space_id):
            raise ConfigurationError(
                "DATABRICKS_GENIE_SPACE_ID contains unsupported characters."
            )
        if workspace_id:
            raise ConfigurationError(
                "Remove DATABRICKS_WORKSPACE_ID for genie-agent mode; it is unused."
            )
    else:
        workspace_id = _required(values, "DATABRICKS_WORKSPACE_ID")
        if not _WORKSPACE_ID.fullmatch(workspace_id):
            raise ConfigurationError(
                "DATABRICKS_WORKSPACE_ID must be a positive decimal identifier."
            )
        if space_id:
            raise ConfigurationError(
                "Remove DATABRICKS_GENIE_SPACE_ID for genie-one mode; "
                "Genie One is not scoped to a space."
            )
        if connection_mode != "existing-oauth":
            raise ConfigurationError(
                "Genie One requires FOUNDRY_CONNECTION_MODE=existing-oauth. "
                "The managed connector's ai-gateway scope support is unverified. "
                "Provision a custom OAuth connection using docs/custom-oauth.md."
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
        databricks_integration_mode=mode,
        databricks_workspace_id=workspace_id,
        foundry_connection_mode=connection_mode,
    )
