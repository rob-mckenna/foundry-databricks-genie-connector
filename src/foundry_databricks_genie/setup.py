"""Shared, secret-free azd orchestration for both shell entry points."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

from .config import Configuration, ConfigurationError


def preflight() -> None:
    if shutil.which("azd") is None:
        raise ConfigurationError("Missing required command: azd.")


def render_toolbox(connection_name: str) -> str:
    return (
        "description: Azure Databricks Genie tools exposed through a managed "
        "Foundry Toolbox.\n"
        "connections:\n"
        f"  - name: {connection_name}\n"
    )


def write_toolbox(path: Path, connection_name: str) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render_toolbox(connection_name), encoding="utf-8")
    except OSError as error:
        raise ConfigurationError("Could not write the Toolbox configuration.") from error


def parse_json(text: str) -> object:
    try:
        document: object = json.loads(text.lstrip("\ufeff"))
        return document
    except json.JSONDecodeError as error:
        # CLI output can contain credentials; never echo it into a diagnostic.
        raise ConfigurationError("Expected valid JSON from azd or the input file.") from error


def _record(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ConfigurationError("Expected a resource object in the azd response.")
    return value


def _properties(document: dict[str, object]) -> dict[str, object]:
    return _record(document["properties"]) if "properties" in document else document


def resource_list(document: object, collection: str) -> list[dict[str, object]]:
    if isinstance(document, dict):
        if document.get("nextLink") or document.get("next_link"):
            raise ConfigurationError(
                "The azd resource list is incomplete. Upgrade the Foundry extensions "
                "or use manual setup; no resource absence can be inferred."
            )
        document = document.get("value", document.get(collection))
    if not isinstance(document, list):
        raise ConfigurationError("Expected a complete resource list from azd.")
    return [_record(item) for item in document]


def resource_exists(document: object, collection: str, name: str) -> bool:
    names: list[str] = []
    for item in resource_list(document, collection):
        item_name = item.get("name")
        if not isinstance(item_name, str) or not item_name:
            raise ConfigurationError("A resource in the azd list has no valid name.")
        names.append(item_name)
    if len(names) != len(set(names)):
        raise ConfigurationError("The azd resource list contains duplicate names.")
    return name in names


def assert_connection(
    document: object,
    expected_name: str,
    expected_target: str,
    *,
    require_oauth: bool = False,
    required_scopes: tuple[str, ...] = (),
) -> None:
    record = _record(document)
    properties = _properties(record)
    if record.get("name") != expected_name:
        raise ConfigurationError(
            "The project connection name does not match the configuration."
        )
    target = properties.get("target")
    if isinstance(target, str) and "?" not in expected_target:
        target = target.rstrip("/")
        expected_target = expected_target.rstrip("/")
    if target != expected_target:
        raise ConfigurationError(
            "The project connection targets a different MCP endpoint. "
            "Choose a new connection name, or explicitly replace a managed connection "
            "only after reviewing every consumer."
        )
    if not require_oauth:
        return
    auth_type = properties.get("authType", properties.get("auth_type"))
    credentials = properties.get("credentials")
    if auth_type is None and isinstance(credentials, dict):
        auth_type = credentials.get("type")
    if not isinstance(auth_type, str) or auth_type.lower() != "oauth2":
        raise ConfigurationError(
            "The connection must expose OAuth2 authentication. Unknown, shared-key "
            "and identity-based authentication are not accepted by this setup."
        )
    category = properties.get("category", properties.get("type"))
    if category is not None and category not in ("RemoteTool", "remote-tool"):
        raise ConfigurationError("The connection must be a RemoteTool connection.")
    if required_scopes:
        scopes = properties.get("scopes")
        if scopes is None:
            print(
                "WARNING: azd did not expose OAuth scopes. Scope and refresh "
                "validation are NOT VERIFIED; verify the connection in Foundry "
                "and complete the live validation procedure before using it.",
                file=sys.stderr,
            )
        else:
            if isinstance(scopes, str):
                actual_scopes = set(re.split(r"[\s,]+", scopes.strip()))
            elif isinstance(scopes, list) and all(isinstance(s, str) for s in scopes):
                actual_scopes = set(scopes)
            else:
                raise ConfigurationError("The connection's OAuth scopes are malformed.")
            if not set(required_scopes).issubset(actual_scopes):
                raise ConfigurationError(
                    "The connection is missing required OAuth scopes: "
                    + " ".join(required_scopes)
                    + ". Update the custom OAuth app and connection, then re-consent."
                )


def assert_toolbox_connections(document: object, expected_name: str) -> None:
    for item in resource_list(document, "connections"):
        name = item.get(
            "connectionName",
            item.get("connection_name", item.get("project_connection_id", item.get("name"))),
        )
        if name == expected_name:
            return
    raise ConfigurationError(
        "The Toolbox does not reference the configured project connection. "
        "Choose a new Toolbox name or reconcile it manually."
    )


def _run_azd(configuration: Configuration, *arguments: str) -> str:
    command = [
        "azd", "ai", *arguments,
        "--project-endpoint", configuration.foundry_project_endpoint,
        "--output", "json", "--no-prompt",
    ]
    operation = " ".join(arguments[:2])
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, encoding="utf-8",
            timeout=120, check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise ConfigurationError(
            f"azd {operation} timed out. Inspect resource state before retrying; "
            "a requested change may have completed."
        ) from error
    except (OSError, UnicodeError) as error:
        raise ConfigurationError(f"Could not execute azd {operation}.") from error
    if result.returncode != 0:
        raise ConfigurationError(
            f"azd {operation} failed (exit {result.returncode}). "
            "Check authentication, project permissions, connectivity and extension "
            "versions. Raw CLI output is withheld because it may contain secrets. "
            "Inspect diagnostics privately; a failed lookup is not resource absence."
        )
    return result.stdout


def setup(
    configuration: Configuration,
    output: Path,
    *,
    replace_connection: bool = False,
) -> None:
    if (
        configuration.databricks_integration_mode == "genie-one"
        and configuration.foundry_connection_mode != "existing-oauth"
    ):
        raise ConfigurationError(
            "Genie One managed OAuth scope support is unverified. "
            "Use an existing OAuth connection."
        )
    if replace_connection and configuration.foundry_connection_mode == "existing-oauth":
        raise ConfigurationError(
            "Replacement is not allowed with existing-oauth. Manage this connection "
            "in Foundry or choose a new connection name."
        )
    preflight()
    connection_name = configuration.foundry_connection_name
    toolbox_name = configuration.foundry_toolbox_name

    def query(*arguments: str) -> object:
        return parse_json(_run_azd(configuration, *arguments))

    connection_exists = resource_exists(query("connection", "list"), "connections", connection_name)
    toolbox_exists = resource_exists(query("toolbox", "list"), "toolboxes", toolbox_name)
    if configuration.foundry_connection_mode == "existing-oauth" and not connection_exists:
        raise ConfigurationError(
            "The existing OAuth connection was not found. Provision it in Foundry "
            "using docs/custom-oauth.md before running setup."
        )
    required_scopes = (
        configuration.required_oauth_scopes
        if configuration.foundry_connection_mode == "existing-oauth"
        else ()
    )

    def verify_connection() -> None:
        assert_connection(
            query("connection", "show", connection_name),
            connection_name, configuration.genie_mcp_endpoint,
            require_oauth=True, required_scopes=required_scopes,
        )

    if connection_exists and not replace_connection:
        verify_connection()
    # Check both existing resources before changing either one.
    if toolbox_exists:
        assert_toolbox_connections(
            query("toolbox", "connection", "list", toolbox_name), connection_name
        )
    write_toolbox(output, connection_name)
    if not connection_exists or replace_connection:
        arguments = [
            "connection", "create", connection_name,
            "--kind", "remote-tool", "--target", configuration.genie_mcp_endpoint,
            "--auth-type", "oauth2", "--connector-name", "foundrydatabricksmcp",
        ]
        if connection_exists:
            print(
                "WARNING: replacing the shared connection affects every consumer.",
                file=sys.stderr,
            )
            arguments.append("--force")
        _run_azd(configuration, *arguments)
        verify_connection()
    if not toolbox_exists:
        _run_azd(
            configuration, "toolbox", "create", toolbox_name,
            "--from-file", str(output),
        )
        assert_toolbox_connections(
            query("toolbox", "connection", "list", toolbox_name), connection_name
        )
    print("Setup resource checks completed; end-to-end integration is NOT TESTED.")
    print(f"Mode: {configuration.databricks_integration_mode}")
    print(f"Connection: {connection_name}")
    print(f"Toolbox: {toolbox_name}")
    print(f"Toolbox consumer endpoint: {configuration.toolbox_mcp_endpoint}")
    print("Attach an agent, complete per-user OAuth consent, and follow docs/validation.md.")
