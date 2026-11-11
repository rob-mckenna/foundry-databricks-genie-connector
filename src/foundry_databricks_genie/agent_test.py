"""Inspect and invoke an existing agent without provisioning or modifying it."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING
from urllib.parse import parse_qs, urlparse

from .bootstrap import _assert_active_routing
from .config import Configuration, ConfigurationError, validate_foundry_project
from .setup import _record
from .smoke import run_smoke

if TYPE_CHECKING:
    from azure.ai.projects import AIProjectClient


@dataclass(frozen=True)
class AgentTestTarget:
    agent_version: str
    toolbox_version: str
    model: str
    server_label: str
    approvals_required: bool


def inspect_agent(
    project: AIProjectClient, configuration: Configuration, agent_name: str
) -> AgentTestTarget:
    agent = project.agents.get(agent_name).as_dict()
    latest = _record(_record(agent.get("versions")).get("latest"))
    version = latest.get("version")
    if not isinstance(version, str) or not version or latest.get("status") != "active":
        raise ConfigurationError("The existing agent must have an active version.")
    _assert_active_routing(agent, version)
    definition = _record(latest.get("definition"))
    tools = definition.get("tools")
    if (
        definition.get("kind") != "prompt" or definition.get("skills") or definition.get("harness")
        or not isinstance(tools, list) or len(tools) != 1
    ):
        raise ConfigurationError("test-agent requires a prompt agent with only one Toolbox MCP tool.")
    tool = _record(tools[0])
    model = definition.get("model")
    label = tool.get("server_label")
    if (
        tool.get("type") != "mcp" or tool.get("headers") or tool.get("authorization")
        or tool.get("connector_id") or tool.get("tunnel_id")
        or not isinstance(label, str) or not label
        or not isinstance(model, str) or not model
    ):
        raise ConfigurationError("The saved agent has an unsupported tool or model configuration.")
    target = tool.get("server_url")
    if not isinstance(target, str):
        raise ConfigurationError("The saved MCP tool must have a Toolbox URL.")
    try:
        url = urlparse(target)
        expected = urlparse(configuration.foundry_project_endpoint)
        port = url.port
    except ValueError as error:
        raise ConfigurationError("The saved Toolbox URL is invalid.") from error
    path_prefix = expected.path.rstrip("/") + "/toolboxes/" + configuration.foundry_toolbox_name
    path_match = re.fullmatch(re.escape(path_prefix) + r"/versions/([A-Za-z0-9_-]+)/mcp", url.path)
    if (
        url.scheme != "https" or url.hostname != expected.hostname or port not in (None, 443)
        or url.username is not None or url.password is not None or url.fragment
        or "\\" in target or any(character.isspace() for character in target)
        or parse_qs(url.query, keep_blank_values=True) != {"api-version": ["v1"]}
        or path_match is None
    ):
        raise ConfigurationError(
            "The saved Toolbox URL must use the configured project's hostname and Toolbox "
            "with an explicit version and api-version=v1. Correct the saved agent; "
            "test-agent will not rewrite it."
        )
    toolbox_version = path_match.group(1)
    box = project.toolboxes.get_version(
        configuration.foundry_toolbox_name, toolbox_version
    ).as_dict()
    box_tools = box.get("tools")
    if box.get("skills") or not isinstance(box_tools, list) or len(box_tools) != 1:
        raise ConfigurationError("The pinned Toolbox must contain only the configured Genie MCP tool.")
    source = _record(box_tools[0])
    connection = project.connections.get(
        configuration.foundry_connection_name, include_credentials=False
    )
    connection_data = connection.as_dict()
    if (
        source.get("type") != "mcp" or source.get("headers") or source.get("authorization")
        or source.get("connector_id") or source.get("tunnel_id")
        or source.get("project_connection_id") not in (connection.name, connection.id)
        or source.get("server_url") not in (None, configuration.genie_mcp_endpoint)
        or connection.target != configuration.genie_mcp_endpoint
        or _record(connection_data.get("credentials")).get("type") != "OAuth2"
    ):
        raise ConfigurationError("The pinned Toolbox does not match the configured Genie OAuth target.")
    binding_ref = tool.get("project_connection_id")
    if binding_ref:
        if not isinstance(binding_ref, str):
            raise ConfigurationError("The saved agent has an invalid connection reference.")
        binding = project.connections.get(
            binding_ref.rsplit("/", 1)[-1], include_credentials=False
        )
        if binding_ref not in (binding.name, binding.id) or binding.target != target:
            raise ConfigurationError("The agent's existing Toolbox connection does not match its saved URL.")
    return AgentTestTarget(version, toolbox_version, model, label, tool.get("require_approval", "always") == "always")


def invoke_existing(
    project: AIProjectClient, configuration: Configuration, agent_name: str, question: str,
    *, approve_tools: bool = False, non_interactive: bool = False,
) -> int:
    target = inspect_agent(project, configuration, agent_name)
    if not target.approvals_required and not approve_tools:
        raise ConfigurationError(
            "The saved agent can execute tools without approval. Use --approve-tools "
            "to authorize this test, or enable approvals on the agent separately."
        )
    print(f"Testing existing agent: {agent_name}, version {target.agent_version}")
    print(f"Saved model: {target.model}; pinned Toolbox version: {target.toolbox_version}")
    print("No provisioning or configuration changes. Invocation can incur charges and retain data in Foundry.")
    with project.get_openai_client(agent_name=agent_name, max_retries=0, timeout=120) as client:
        result = run_smoke(
            client, configuration.databricks_integration_mode, question,
            approve_tools=approve_tools, non_interactive=non_interactive,
            server_label=target.server_label,
        )
    if inspect_agent(project, configuration, agent_name) != target:
        raise ConfigurationError("The agent or pinned Toolbox selection changed during testing; result not verified.")
    if result == 0:
        print("PASS: existing-agent tool execution observed with matching pre/post wiring checks.")
    return result


def execute_agent_test(
    configuration: Configuration, agent_name: str, question: str,
    *, approve_tools: bool = False, non_interactive: bool = False,
) -> int:
    validate_foundry_project(configuration)
    try:
        from azure.ai.projects import AIProjectClient
        from azure.core.exceptions import AzureError
        from azure.identity import AzureDeveloperCliCredential
        from openai import OpenAIError
    except ImportError as error:
        raise ConfigurationError(
            'Agent-test dependencies are missing. Install: python -m pip install -e ".[bootstrap]"'
        ) from error
    try:
        with AzureDeveloperCliCredential(process_timeout=30) as credential:
            with AIProjectClient(
                endpoint=configuration.foundry_project_endpoint, credential=credential,
                allow_preview=True, retry_total=0, connection_timeout=30, read_timeout=120,
            ) as project:
                return invoke_existing(
                    project, configuration, agent_name, question,
                    approve_tools=approve_tools, non_interactive=non_interactive,
                )
    except (AzureError, OpenAIError) as error:
        raise ConfigurationError(
            "Existing-agent test failed. Check project access, saved wiring, consent and "
            "networking. Raw diagnostics are withheld; inspect the request in Foundry. "
            "No provisioning or configuration changes were performed."
        ) from error
