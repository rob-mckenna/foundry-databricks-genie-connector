# Troubleshooting

## Bootstrap dependencies or model are missing

Install the optional extra with `python -m pip install -e ".[bootstrap]"`.
VS Code must select an interpreter with that extra for import diagnostics to
resolve. The terminal and editor can use different Python environments.
Set `FOUNDRY_MODEL_DEPLOYMENT` to an existing deployment name; bootstrap does
not deploy a model or fall back to another one.

## Bootstrap refuses an existing agent, Toolbox or binding

If the goal is to **test** a portal-created agent rather than provision one,
use `test-agent` instead. It accepts agents without bootstrap ownership
metadata, but validates their real saved Toolbox URL, pinned source and routing.
Do not add ownership metadata just to bypass bootstrap's overwrite protection.
See [existing-agent testing](bootstrap.md#test-an-existing-agent-without-provisioning).

Use a dedicated test-agent name and a Toolbox containing only the selected
Genie MCP connection. Modified/unowned agents, broader Toolboxes, mismatched
pinned versions and incorrect Entra connection audiences are refused.
Choose new names rather than deleting or replacing shared resources.

If active-version routing is missing, mixed or points elsewhere, inspect the
agent endpoint configuration in Foundry. The helper does not guess the route
or silently invoke an unverified version. See [bootstrap safety](bootstrap.md).

## Bootstrap asks for consent or tool approval

Exit code 3 means action is still required, not success. Run interactively
to open the consent page, or authorize in the playground as the same user.
To approve the smoke test's Toolbox calls, explicitly use `--approve-tools`
(`-ApproveTools` in PowerShell); otherwise review calls in the playground.
The saved agent's approval policy remains enabled.

Exit code 4 means the response did not establish the required smoke evidence.
An LLM-only answer, tool discovery, or Genie One `in_progress` response cannot
pass. Check traces privately; do not broaden success detection just to make a
test pass.

## Configuration or mode errors

Run offline `validate` and `endpoint`. Check both the environment file and
shell variables: the shell wins. Remove a space ID when selecting Genie One;
remove a workspace ID when selecting the curated mode. Do not supply a full
MCP URL as `DATABRICKS_WORKSPACE_HOST`.

Genie One requires `FOUNDRY_CONNECTION_MODE=existing-oauth`. The managed
connector's Gateway scope support is unverified, so this is an intentional
error, not a missing CLI flag. Follow [custom OAuth setup](custom-oauth.md).

## Managed MCP Servers is unavailable

The workspace preview is required for the **curated Genie Agent endpoint**.
Do not apply that prerequisite indiscriminately to GA Genie One.
If policy prohibits the curated preview, do not enable it as a workaround.

## azd lookup fails or returns an unfamiliar schema

Setup stops rather than treating failed inspection as a missing resource.
Check `azd auth login`, project access, network connectivity and installed
extensions. Update explicitly with `azd extension update --all` when appropriate.

The offline adapter accepts JSON resource arrays or `value`/collection
envelopes. It rejects incomplete lists and unknown structures. Do not change
it to scan arbitrary nested names or discard error payloads.

Inspect the failed operation privately. Raw CLI output is intentionally not
printed or saved because it might contain credentials. Do not request
`--show-credentials` or attach unreviewed logs to an issue. On timeout or
creation failure, inspect resource state before retrying; creation may have
partly completed. No automatic rollback deletes resources.

## `ParentResourceNotFound` during connection list

If SDK access to the project works but `azd ai connection list` returns
`ParentResourceNotFound`, compare the account name in the failed ARM path
with the actual Azure account resource name. A custom subdomain can differ
from the resource name. In the observed installation, the connection
extension inferred the wrong ARM account name from the hostname.

Do not change a valid project URL to an invented resource-name-based hostname
to satisfy that inference. Use the project's authoritative endpoint and ARM
ID. The successful live validation provisioned isolated test resources using
SDK/ARM calls with that ID; the repository bootstrap still depends on the CLI
and will stop on this error. Review an extension fix or supported resource-ID
selection before treating bootstrap provisioning as verified for this layout.

## Existing connection or Toolbox does not match

For `test-agent`, a stale hostname on the remote agent cannot be fixed by
changing `.env` alone. Save a corrected agent version using the authoritative
project endpoint and retain the prior version. A Toolbox resource name is not
an authentication connection name, and a Toolbox's name containing "v2" does
not make its actual version 2.

Check the exact connection name, full target (including Genie One's `o`
parameter), OAuth2 authentication type and Toolbox connection reference.
Prefer new resource names for a different mode or target.

Only `managed-oauth` accepts `-ReplaceConnection` / `--replace-connection`.
That option affects all consumers and is not isolated by Toolbox versioning.
`existing-oauth` never permits script replacement. Reconcile it in Foundry or
provision a new connection.

## Scope validation is NOT VERIFIED

Some CLI versions may omit OAuth scopes from non-secret inspection. Setup
emits a warning and does not claim token validation. Verify the app-allowed
and connection-requested scopes in Foundry/Databricks:

- Genie One: `ai-gateway offline_access`
- Curated Genie Agent: `genie offline_access`

If the connection exposes a wrong scope set, setup fails. Updating only the
URL does not update an existing grant. Re-consent after scope/app changes.
Managed scope overrides are not supported by adding `--scopes` alongside
`--connector-name`.

## Consent is required, declined, expired or revoked

`CONSENT_REQUIRED` (MCP code `-32006`) or `oauth_consent_request` is expected
when a user first authorizes that connection/project. Open the returned link,
complete authorization, and resume/retry the request. Declining consent is a
failure that the application must explain, not a successful empty answer.
Refresh expiry/revocation can require new consent.

## `ARA request failed with status BadRequest` during `tools/list`

This is token acquisition failing during MCP discovery, before a Genie query.
Changing the question, model or SQL does not repair provider authorization.
HTTP 200 around a JSON-RPC error is not a successful tool discovery.

First distinguish this from normal `CONSENT_REQUIRED` / `oauth_consent_request`:

- Confirm the target and managed connector name through non-secret connection
  metadata. A valid OAuth2 resource is not proof of a usable per-user grant.
- Confirm whether Databricks sign-in and consent have been completed for this
  connection/project/user.
- Open the Databricks tool/connection in Foundry and use its supported
  connection/authorization experience to initiate sign-in. Do not share
  credentials or consent links in logs or chat.
- If no authorization action is available, or it returns the same broker
  error, have an administrator verify the managed connector configuration
  and availability. Do not assume missing consent is the sole cause: normally
  Foundry should surface a consent request.
- A separately named connection created through the supported catalog flow,
  or a properly registered [custom OAuth connection](custom-oauth.md), can be
  evaluated without replacing a shared connection. Do not invent catalog IDs,
  copy another provider's metadata, or add custom scopes to a managed connector.

In a live curated-mode check, MCP initialization succeeded but direct Toolbox
`tools/list` reproduced the ARA error without an agent/model invocation.
This isolated the failure to downstream managed-OAuth discovery, not the
agent-to-Toolbox binding. The underlying broker cause and successful provider
authorization remain unverified; provisioning success must not be reported
as end-to-end integration success.

If a custom OAuth connection also fails after its exact callback, provider
URLs and scopes have been verified, isolate it with direct MCP discovery
through Responses, retaining tool approval. If that path returns the same
ARA error, changing only Toolbox wiring is not a sufficient repair. Record the
request ID privately and seek Foundry-side diagnosis; do not conclude that
the provider secret is valid merely because it is stored.

Credential inspection is not part of routine setup. Any diagnostic read of
stored secrets requires explicit operator approval and must keep values out
of console output, logs, local files and chat. The SDK may expose credential
field names in lowercase; inspect the schema before interpreting missing
field lookups as missing credentials.

## Consent succeeds but calls fail

- **401/authentication:** check provider token configuration, target workspace,
  requested scopes, callback registration and expiry without printing tokens.
- **403/authorization:** check Foundry access separately from Gateway service,
  Genie Agent and data privileges. Validate the actual downstream user.
- **Missing/empty data:** verify the user's Unity Catalog access; curated
  Genie can return an empty response for inaccessible data. Do not assume this
  is a valid business result without checking permissions.
- **Hosted agent only:** verify per-request user context reaches Toolbox
  through the supported hosting integration.
- **Network failure:** verify Foundry-to-Databricks reachability, not only
  local-to-Databricks access. Do not weaken TLS or IP/network controls.

## Genie One never returns a final answer

Tool discovery or `genie_ask` returning `in_progress` is not query completion.
Allow the agent to invoke `genie_poll_response` sequentially until terminal
status, handle failed/incomplete responses, and retrieve larger results only
when needed. Do not assume Foundry renders MCP Apps views.

## OAuth application changes are not visible yet

Databricks documents up to 30 minutes for propagation. Check configuration
and grants before retrying; do not repeatedly replace a shared connection.

## Old beta URL stops working

The **unsuffixed** `/api/2.0/mcp/genie` reaches EOL November 30, 2026.
This is different from `/api/2.0/mcp/genie/<space-id>`.
Follow [migration](migration.md), not a repository-wide blind URL replacement.
