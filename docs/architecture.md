# Architecture and modernization decisions

Documentation reviewed on **2026-10-30**. Product documentation is the authority;
offline tests establish repository behavior, not cloud service compatibility.

## Before and after

Previously, the only route was a Foundry Toolbox referencing a
`foundrydatabricksmcp` managed OAuth connection targeting
`https://<workspace>/api/2.0/mcp/genie/<space-id>`.
The Python package validated configuration; two shell scripts duplicated the
provisioning flow. Authorization was described broadly as user OAuth plus
Genie/Unity Catalog access.

That route remains documented and useful. The modernization adds Genie One
without removing or silently repointing the curated route:

```text
                  Microsoft Foundry project
  Agent A -----+
  Agent B -----+--> Toolbox --> OAuth connection for the selected target
                                  |
              +-------------------+---------------------+
              |                                         |
     Mode: genie-one                           Mode: genie-agent
     Unity Gateway                             Workspace managed MCP
     system.ai.genie_one_mcp                    /api/2.0/mcp/genie/<space-id>
     Genie One / Genie Ontology                Selected Genie Agent
              |                                         |
     Gateway grants/policies                   Genie Agent ACLs
              |                                         |
              +---- Underlying resource permissions ----+
                         Unity Catalog data
```

Each deployed Toolbox/connection pair selects one mode and target. Deploy
another pair with distinct names if both are needed. Multiple agents may
reuse a pair; there is no assumption that one connection targets two servers.

## Discovery assessment

| Area | Decision |
| --- | --- |
| Reusable Toolbox/project connection | Retain; Microsoft explicitly documents reuse across agents and runtimes |
| Managed Databricks OAuth connector | Retain for curated Genie Agent; Genie One scope compatibility is unverified |
| Existing space-specific MCP URL | Retain as `genie-agent`; no EOL was established for this endpoint |
| Genie One | Add the documented Gateway service, workspace query parameter, and separate scope requirements |
| Local configuration | Retain non-secret environment pattern and override precedence |
| Provisioning | Share one Python `azd` routine behind the two existing shell entry points |
| Error handling | Stop on failed/malformed/incomplete lookups; do not infer absence or print raw CLI payloads |
| Existing-resource assertions | Match explicit resource fields, OAuth type and target; inspect scopes when exposed |
| Documentation | Replace blanket lifecycle claims; distinguish compute, data and Gateway permissions |
| Tests | Preserve original endpoint coverage; add modes, setup paths, failures and hygiene regression tests |

The base connector introduces no model, agent application, custom MCP proxy,
token cache, cloud SDK dependency or infrastructure.

The optional [guided bootstrap](bootstrap.md) adds an SDK dependency extra and
creates a dedicated declarative prompt agent. Its MCP tool references a second
project connection, using `UserEntraToken` with audience `https://ai.azure.com`,
to authenticate to a pinned Toolbox endpoint. The original Databricks OAuth
connection remains downstream of the Toolbox. No model deployment, hosted
agent container, custom OAuth registration or permission grant is created.
The SDK binds smoke tests to the agent's current endpoint and verifies active
version routing before and after the test.

## Mode contracts

### Genie One

```text
https://<workspace-hostname>/ai-gateway/mcp-services/system.ai.genie_one_mcp?o=<workspace-id>
```

The service-specific documentation includes the `o` query parameter; the
implementation follows that more specific contract rather than the generic
Gateway URL example. Workspace ID is explicitly configured, not inferred from
a hostname. A Genie space ID is not meaningful in this mode.

Genie One answers workspace-wide business questions using Genie Ontology.
`genie_ask` starts a response, `genie_poll_response` follows it to completion,
and `genie_get_query_result` retrieves larger results when needed. Responses
can still be truncated. Conversation continuation uses `conversation_id`.
Do not overlap polls. Cancellation uses `genie_cancel_response`. MCP Apps
clients can receive `view_ask`; rendering those views in Foundry is not
verified here. The connector itself does not implement agent orchestration.

### Curated Genie Agent

```text
https://<workspace-hostname>/api/2.0/mcp/genie/<space-id>
```

This route uses a selected Genie Agent's tables, instructions and examples
(up to 50 tables/views/metric views per the current documentation). It is
read-only and does not pass conversation history to the Genie API.
Calls bypass Unity Gateway tracing, MCP grants, policies and guardrails.

## OAuth boundary

Both routes retain per-user OAuth project connections. `managed-oauth` uses
Foundry's app; `existing-oauth` normally uses a custom Databricks OAuth app
whose tokens are still managed by Foundry.

Microsoft lists `foundrydatabricksmcp` but does not establish its
`ai-gateway` scope support in the sources reviewed. Managed connectors supply
their own scopes: do not add custom scope/client flags to a managed connection.
Accordingly, Genie One setup requires an existing OAuth connection and never
creates/replaces a managed connector.

No claim is made that a Microsoft Entra access token for Foundry can be
forwarded to Databricks. Provider OAuth sign-in, Entra user delegation, and
Databricks-hosted-agent OBO are distinct mechanisms. See
[authentication](custom-oauth.md) and [security](security.md).

## Reuse, versions and user context

Toolbox definitions reference project connection names, not credentials.
The consumer endpoint serves the default Toolbox version:

```text
<project-endpoint>/toolboxes/<toolbox-name>/mcp?api-version=v1
```

Test a candidate version before promotion:

```text
<project-endpoint>/toolboxes/<toolbox-name>/versions/<version>/mcp?api-version=v1
```

This setup does not modify existing Toolbox versions or promote defaults.
Replacing a connection is not isolated by a Toolbox version: all references
to that connection can be affected. Prefer new names when migrating.

Foundry documents OAuth consent per user, connection name and project.
Agent identity gates Toolbox access; the provider-authorized user determines
Databricks data access. For hosted agents, an agent credential alone does not
carry the user's context. Use the supported Foundry hosting integration to
forward the current `x-agent-foundry-call-id`; never hard-code or reuse it
between requests. Cross-agent reuse and concurrent-user isolation still need
[live testing](validation.md).

## Lifecycle and authoritative source register

| Component | Verified statement / limitation | Source |
| --- | --- | --- |
| Genie One MCP | GA service `system.ai.genie_one_mcp` | [Genie One](https://learn.microsoft.com/azure/databricks/agents/mcp-tools/genie-mcp) |
| Unsuffixed Genie One beta URL | `/api/2.0/mcp/genie` is deprecated; EOL November 30, 2026 | [Genie One migration notice](https://learn.microsoft.com/azure/databricks/agents/mcp-tools/genie-mcp#access-through-unity-gateway) |
| Curated Genie Agent MCP | Public Preview; space-specific endpoint remains documented | [Genie Agent MCP](https://learn.microsoft.com/azure/databricks/agents/mcp-tools/genie-agent) |
| Databricks MCP / Unity Gateway | Status is capability-specific; other `system.ai` services require Gateway beta enablement; do not transfer that requirement to GA Genie One | [Databricks-provided MCPs](https://learn.microsoft.com/azure/databricks/agents/mcp-tools/built-in-mcp-services) |
| Foundry Toolbox | Reusable managed endpoint and connection references documented; a separate blanket GA declaration was not established here | [Overview](https://learn.microsoft.com/azure/foundry/agents/concepts/toolbox-overview), [setup/versioning](https://learn.microsoft.com/azure/foundry/agents/how-to/tools/toolbox) |
| Foundry MCP / managed OAuth | Supported configuration and Databricks connector are documented; no independent end-to-end GA or Genie One compatibility claim | [MCP configuration](https://learn.microsoft.com/azure/foundry/agents/how-to/tools/model-context-protocol) |
| Foundry OAuth | Per-user consent, managed/custom applications and refresh | [MCP authentication](https://learn.microsoft.com/azure/foundry/agents/how-to/mcp-authentication), [Toolbox identity boundary](https://learn.microsoft.com/azure/foundry/agents/how-to/tools/tool-authentication) |
| Databricks OAuth | Gateway scope, preconfigured clients, Streamable HTTP and refresh | [Other MCP clients](https://learn.microsoft.com/azure/databricks/ai-gateway/coding-agent-mcp-skills#other-mcp-clients), [OAuth applications](https://learn.microsoft.com/azure/databricks/integrations/enable-disable-oauth) |
| Gateway authorization | Service/parent grants, workspace assignment, inherited grants | [Govern an MCP](https://learn.microsoft.com/azure/databricks/ai-gateway/govern-mcp-service) |
| Curated authorization | Embedded compute credentials versus end-user data access | [Share a Genie Agent](https://learn.microsoft.com/azure/databricks/genie-agents/set-up#share-a-genie-agent) |

Key remaining risks are managed-connector scope support, deployed CLI response
compatibility, user-context propagation, network reachability, feature/region
availability, and revoked/expired consent. They require explicit validation,
not additional speculative code.
