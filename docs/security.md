# Authentication, authorization and security

## Two authorization planes

### Microsoft Foundry

Foundry controls project access, connection administration, Toolbox authoring,
agent execution and access to the Toolbox itself. It does not grant
Databricks resource or data permissions.

| Actor | Documented access / responsibility |
| --- | --- |
| Connection operator | Foundry Project Manager for creating project connections |
| Toolbox developer / interactive agent tester | Foundry User as specified by Toolbox/MCP prerequisites |
| Prompt-agent runtime identity | Project access required by Toolbox prerequisites |
| End user | Project access for the selected runtime; Toolbox prerequisites specify Foundry User for OAuth users, while the runtime authentication guide specifies at least Foundry Agent Consumer for consumers of an OAuth-enabled agent |

Apply the role guidance for the exact client/runtime; do not promote all
runtime consumers to connection administrators. Custom roles must include the
applicable resource operations. No roles are granted by the setup scripts.

Sources: [MCP prerequisites](https://learn.microsoft.com/azure/foundry/agents/how-to/tools/model-context-protocol),
[Toolbox prerequisites](https://learn.microsoft.com/azure/foundry/agents/how-to/tools/toolbox),
[runtime authentication](https://learn.microsoft.com/azure/foundry/agents/how-to/tools/tool-authentication).

### Azure Databricks: Genie One

The authenticated Databricks caller needs:

- Workspace assignment and an applicable entitlement. Consumer access can
  support Gateway MCP use; managing MCPs in the UI requires Workspace access.
- `EXECUTE` on `system.ai.genie_one_mcp`.
- `USE CATALOG` on `system` and `USE SCHEMA` on `system.ai`, per the service's
  parent-grant requirements.
- Applicable permissions on underlying data/resources, including catalog/
  schema access and data privileges such as `SELECT`.
- Compliance with applicable Unity Gateway service policies.

Review inherited/default `EXECUTE` grants on `system.ai`; a single explicit
grant does not necessarily restrict a broadly shared service. Metastore
administrators follow the documented `MANAGE` procedure to administer
Databricks-provided MCP grants. End users do **not** need `USE CONNECTION`
merely to invoke the MCP; do not grant it as a troubleshooting shortcut.

Sources: [Gateway authorization](https://learn.microsoft.com/azure/databricks/ai-gateway/govern-mcp-service),
[MCP authentication and entitlements](https://learn.microsoft.com/azure/databricks/agents/mcp-tools/authentication-networking).

### Azure Databricks: curated Genie Agent

- A workspace administrator enables the Managed MCP Servers preview.
- Users need the applicable consumer/Databricks SQL entitlement, Genie Agent
  ACLs (CAN VIEW/CAN RUN as applicable), and underlying Unity Catalog access.
- Data authorization is evaluated as the end user, including applicable row
  filters and column masks.
- Compute uses the embedded credentials of the author who configured the SQL
  warehouse. Authors need appropriate warehouse access; end users do not
  necessarily need direct warehouse permissions.
- This endpoint bypasses Gateway MCP grants, policies, tracing and guardrails.

Sources: [Genie Agent MCP](https://learn.microsoft.com/azure/databricks/agents/mcp-tools/genie-agent),
[sharing and data access](https://learn.microsoft.com/azure/databricks/genie-agents/set-up#share-a-genie-agent).

## Identity propagation

OAuth API scopes are separate from resource grants. Foundry authorizes the
agent/client at its boundary; Databricks authorizes the provider-authenticated
user at its own boundary. Users of the same connection must not share one
cached application token.

For hosted agents, use Foundry's hosting integration for per-request user
context. The agent's service credential alone is not sufficient. Never
hard-code or reuse `x-agent-foundry-call-id` across users/requests.
The Foundry authentication guide also documents same-tenant requirements for
agent consumers; do not assume cross-tenant exchange works.

Databricks supports service-principal authentication for some workloads, but
that changes the authorized identity. This reference setup deliberately
retains per-user OAuth rather than adding a shared service-principal fallback.

## Configuration and logging

The optional bootstrap obtains Foundry access tokens through
`AzureDeveloperCliCredential` in memory; it never stores them in agent
definitions or sends them to Databricks. Its extra `UserEntraToken` connection
targets the Toolbox, not the Databricks endpoint. Do not enable verbose SDK/
HTTP diagnostics in shared logs.
When data-plane projections omit the binding audience, bootstrap also uses
the operator's identity for a read-only ARM connection lookup. The operator
must have management-plane read access to that project connection. This path
never requests connection secrets or grants additional permissions.

Bootstrap keeps saved-agent tool approval enabled. Its `--approve-tools`
option authorizes calls only during the requested smoke test, after verifying
that the Toolbox contains only the configured Genie connection. It does not
bypass provider consent. Consent URLs are opened only after interactive
confirmation of the HTTPS host and are not printed or saved.

Smoke questions and results are not logged locally, but invoking Responses
can store them in Foundry. Use approved synthetic data and review platform
retention. A passing transport test does not prove data authorization or
answer correctness.

- Keep `.env`, its local variants and `.generated` out of Git. The example
  file contains placeholders only.
- Never put tokens, client secrets or keys in configuration, arguments,
  transcripts, chat, issues, or captured responses.
- Setup does not use `--show-credentials` or persist connection payloads.
  It captures CLI output and reports operation/exit status without echoing
  payloads, which could contain secrets. Inspect detailed errors privately.
- Offline `config`/`endpoint` commands and the printed Toolbox endpoint expose
  non-secret but private deployment metadata; do not publish it.
- Do not disable TLS verification or weaken authentication to pass tests.
- Treat prompts, SQL, results, citations and consent links as potentially
  sensitive. Minimize retained results and access to traces.

The repository's pattern scan is not a complete secret detector or a Git
history audit. Review changes and use approved secret-scanning tooling.
Rotate exposed credentials; deleting a working-tree value does not revoke it.

## Production review

Review feature-specific lifecycle, availability, networking, residency,
Databricks partner-powered AI settings, costs, consent/refresh policy, audit
retention, prompt injection/tool approval policy and operational ownership.
Genie One can return more data than a single model response can hold; control
result retrieval and avoid dumping full results into logs.

Run [positive and negative authorization tests](validation.md) for each mode.
Successful provisioning is never authorization evidence.
