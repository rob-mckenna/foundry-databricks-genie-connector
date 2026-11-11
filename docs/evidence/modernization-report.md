# Historical modernization evidence

This archived report preserves dated implementation and live-test evidence.
It is not current setup guidance or certification for another deployment.
Use the repository's [validation procedure](../validation.md) for current
acceptance testing.

Date: 2026-10-30. Scope: repository implementation and offline validation.
The initial implementation and offline validation did not mutate cloud resources.
The guided-bootstrap update and subsequent operator-authorized live setup are
recorded below. No resource replacement or deletion was performed.

## Architecture

**Before:** Foundry agents shared a Toolbox backed by a managed OAuth
connection to one space-specific Genie MCP endpoint.

**After:** the reusable Toolbox/connection boundary is preserved, with two
explicit modes:

- `genie-agent`: existing curated workspace MCP route, retained as the
  backward-compatible default.
- `genie-one`: Unity Gateway route to `system.ai.genie_one_mcp`, including
  the configured workspace ID, backed by an existing OAuth connection.

The change is necessary because the modes have different semantic scope,
OAuth API scopes, authorization boundaries and conversation behavior.
[Architecture and authoritative sources](../architecture.md)

## Implementation

| Files | Changes |
| --- | --- |
| [config.py](../../src/foundry_databricks_genie/config.py), [.env.example](../../.env.example) | Mode selection, workspace ID, exact URLs/scopes, compatibility defaults and validation |
| [setup.py](../../src/foundry_databricks_genie/setup.py), [cli.py](../../src/foundry_databricks_genie/cli.py) | Shared setup, strict resource matching, OAuth checks, safe subprocess diagnostics and opt-in provisioning command |
| [setup.ps1](../../scripts/setup.ps1), [setup.sh](../../scripts/setup.sh) | Preserve shell interfaces while delegating to the shared implementation |
| [Toolbox template](../../config/toolbox.yaml.template) | Match renderer output; regression test prevents drift |
| [.gitignore](../../.gitignore), [hygiene tests](../../tests/test_repository_hygiene.py) | Ignore local environment variants; check actual Git tracking without deleting local configuration |
| [configuration tests](../../tests/test_config.py), [setup tests](../../tests/test_setup.py), [script tests](../../tests/test_scripts.py) | Mode, endpoint, error, scope, resource reuse, replacement and wrapper coverage |
| [CI](../../.github/workflows/ci.yml) | Windows/Linux and Python 3.10/3.12 matrix; both shell syntax checks |
| [README](../../README.md), [architecture](../architecture.md), [manual setup](../manual-setup.md), [custom OAuth](../custom-oauth.md), [security](../security.md), [troubleshooting](../troubleshooting.md), [SECURITY](../../SECURITY.md), [CONTRIBUTING](../../CONTRIBUTING.md) | Align guidance with the implementation and verified product distinctions |
| [migration](../migration.md), [validation](../validation.md), this report | Migration decisions, live acceptance procedure and evidence |

The base package remains dependency-free, with no token cache or hosted-agent
framework. The follow-up below adds optional SDK dependencies. Local environment
values and existing generated files were not changed.

## Authentication

Previously, scripts only created the `foundrydatabricksmcp` managed connector.
That remains the default for curated Genie Agents. Both modes can now reuse
an existing OAuth2 project connection.

Genie One requires `ai-gateway`; curated Genie Agent uses `genie`.
The custom OAuth pattern additionally requires `offline_access` for refresh.
Setup checks these scopes if exposed by non-secret connection inspection;
otherwise it emits an explicit **NOT VERIFIED** warning.

Automatic managed OAuth for Genie One is blocked because the reviewed
documentation does not establish the connector's Gateway scope support.
There is no PAT/shared-identity fallback and no managed scope override.
Custom OAuth registration remains an administrative operation outside the
repository; Foundry still manages the resulting user tokens.

Consent reuse, refresh, revocation, actual token audience and identity
propagation require live validation.

## Authorization

Foundry project/Toolbox access is separate from Databricks authorization.
Connection management requires the applicable Foundry administrator role;
runtime users and agent identities require the roles appropriate to their
client/runtime. See the [role distinctions](../security.md).

Genie One adds Gateway service `EXECUTE`, parent catalog/schema access and
policies, alongside underlying resource permissions. Curated Genie Agent
uses its agent ACLs and underlying Unity Catalog permissions and bypasses
Gateway governance. For curated agents, warehouse compute uses the configured
author's credentials while data access uses the end user's identity.

None of those grants is created or tested by offline setup tests.

## Integration modes and migration

Use Genie One for workspace-wide analytics grounded in Genie Ontology.
Use a curated Genie Agent for a selected, bounded data/instruction context.
Genie One's asynchronous tools and conversational continuation are not
equivalent to the curated MCP interface.

Existing configurations retain curated-agent defaults. Genie One is opt-in:
add a workspace ID, remove the inactive space ID, provision compatible OAuth,
and use distinct connection/Toolbox names before migrating consumers.

The unsuffixed beta URL `/api/2.0/mcp/genie` reaches EOL November 30, 2026.
The existing `/api/2.0/mcp/genie/<space-id>` route is a different, still
documented Public Preview interface. No blanket removal was performed.

Intentional stricter checks reject malformed configuration, unknown OAuth
types, mismatched resources, incomplete lists and exposed incompatible scopes.
Replacement remains explicit for managed connections and is prohibited for
existing-OAuth connections. All consumers of a replaced connection can be
affected, regardless of Toolbox version.

## Validation

| Check | Result | Evidence / limitation |
| --- | --- | --- |
| Baseline tests | FAIL, corrected | 12 passed; one test incorrectly rejected an ignored local environment file |
| Initial modernization offline suite | PASS | 46 tests on local Windows/Python 3.11; mocked cloud responses, no skipped tests |
| Both shell wrappers | PASS | Executed with synthetic invalid configuration and paths containing spaces; errors propagated before cloud access |
| Shell syntax | PASS | Git Bash `bash -n` and PowerShell parser |
| Python compilation | PASS | `python -m compileall -q src tests` |
| Pylance diagnostics | PASS | No diagnostics reported; configuration loader call sites remained compatible |
| Wheel build | PASS | `pip wheel --no-deps` with isolated declared build dependencies |
| Wheel execution | PASS | Imported directly from wheel outside the source tree; both modes produced exact expected endpoints; no environment/generated files in wheel |
| Secret/configuration hygiene | PASS, bounded | Tests and scoped source/example credential, private-key and deployment-identifier pattern scan found no matches |
| Local documentation links | PASS | Relative Markdown targets resolve |
| Whitespace checks | PASS | `git diff --check` |
| Installed azd command availability | PASS | Read-only help inspection; this is not service/API validation |
| CI matrix execution | NOT TESTED | Workflow updated, not submitted/executed on GitHub during this work |
| Full secret scan of Git history | NOT TESTED | Bounded worktree scan is not a complete history/security audit |
| Genie One managed-connector scope support | REQUIRES LIVE ENVIRONMENT | Automatic combination deliberately blocked |
| Foundry-to-Databricks end-to-end, both modes | REQUIRES LIVE ENVIRONMENT | No agent invocation, OAuth grant, governed query or live resource mutation performed |
| Cross-agent reuse and user isolation | REQUIRES LIVE ENVIRONMENT | Explicit two-agent/two-user procedure supplied |
| Refresh, revocation, denied access and Gateway policy tests | REQUIRES LIVE ENVIRONMENT | Follow the live acceptance procedure |

The first non-isolated wheel attempt failed because the local interpreter
lacked `bdist_wheel`. Building with the declared, isolated build dependencies
succeeded; no global packages or repository runtime dependencies were added.

## Remaining issues and next action

- Confirm managed connector behavior before considering automated Genie One
  connection creation.
- Confirm non-secret CLI response compatibility against the target deployment;
  unrecognized structures fail rather than being silently accepted.
- Verify scopes if the CLI omits them, then test actual token/identity behavior.
- Review regional/network availability and feature-specific lifecycle; Genie
  One GA is not a blanket GA assertion for the whole stack.
- Test answer quality, asynchronous completion, truncation and citations.
- Execute [live acceptance](../validation.md) in an approved non-production
  environment before customer reuse. Record the tested modes explicitly.

## Follow-up: guided test-agent bootstrap

The optional [bootstrap workflow](../bootstrap.md) now supports:

- Plan-only operation by default; explicit `--apply` for cloud operations.
- Dedicated prompt-agent creation/reuse with ownership and definition checks.
- An existing model deployment, never an automatically provisioned model.
- A pinned Toolbox endpoint authenticated through a separate UserEntraToken
  project connection, retaining the downstream Databricks OAuth connection.
- Current SDK agent-endpoint invocation rather than an invented CLI create
  command or undocumented version-routing request fields.
- Active agent routing checks before and after the smoke test.
- User-approved browser consent, continuation through `previous_response_id`,
  explicit smoke-test tool approvals and non-interactive needs-action status.
- Bounded requests; rejection of LLM-only answers, discovery-only results,
  machine-readable tool errors and unfinished Genie One polling.
- A portal handoff with agent/version information; no guessed deep-link format.

New implementation files are [bootstrap.py](../../src/foundry_databricks_genie/bootstrap.py)
and [smoke.py](../../src/foundry_databricks_genie/smoke.py). The shared CLI, both
shell wrappers, configuration/example, optional package dependencies, tests,
CI and directly related documentation were updated.

The saved agent retains tool approval. `--approve-tools` approves only calls
within that smoke test; it does not disable OAuth consent or permanently
weaken the agent. Custom project hosts/other clouds are rejected before
acquiring platform tokens. Broader Toolboxes and unrelated/modified agents
are rejected, not silently replaced.

### Follow-up validation

| Check | Result | Evidence / limitation |
| --- | --- | --- |
| Full offline suite | PASS | 78 tests with no skips on Windows/Python 3.12 and the bootstrap extra |
| Source type-check | PASS | Pyright: zero errors/warnings, using the installed SDKs and Python 3.10 language compatibility |
| SDK contract and HTTP adapter | PASS | Real SDK serialization, agent-endpoint routing, OAuth-extension parsing and continuation through an offline mock HTTP transport |
| Earlier SDK transport compatibility | PASS | The transport/consent test also passed with installed azure-ai-projects 2.7.0 / openai 3.17.0 on Python 3.11 |
| Consent-link privacy regression | PASS | A test exposed SDK serialization warnings containing a synthetic signed-link marker; scoped warning suppression plus explicit response validation prevents that disclosure |
| Dependency-free plan | PASS | Bootstrap planning executed with Python site packages disabled; no cloud calls/generated output |
| Shell behavior/syntax, compilation and whitespace | PASS | Both entry points exercised; syntax/compile checks and `git diff --check` |
| Wheel packaging | PASS | Package builds with the optional bootstrap dependency metadata |
| Dependency advisory audit | PASS, bounded | pip-audit found no known vulnerabilities in 29 resolved bootstrap dependencies, with zero skipped records; resolved roots were azure-ai-projects 2.9.0 and azure-identity 1.27.0 |
| Declared minimum dependency versions | PASS, bounded | Separate direct-package audit of azure-ai-projects 2.7.0 and azure-identity 1.26.0 found no known vulnerabilities |
| Scoped secret patterns and local documentation links | PASS | Checked repository source/examples and relative documentation targets |
| Live bootstrap, consent, model/Genie queries and role checks | REQUIRES LIVE ENVIRONMENT | No `--apply` execution or live agent query was performed |
| Cross-user isolation, refresh/revocation and answer correctness | REQUIRES LIVE ENVIRONMENT | A successful transport smoke test does not certify these properties |

The shared modernization CVE tool does not support PyPI, so the dependency
check used live pip-audit advisory queries instead of treating model knowledge
as a complete vulnerability scan. The audited dependency closure was resolved
in an isolated temporary environment; it is not a guarantee about every future
installation allowed by the version ranges.

VS Code's selected interpreter must contain the optional extra to resolve SDK
imports. Validation used a separate environment without changing the user's
selected interpreter or installing packages into their global environment.

Next: configure a dedicated agent name and an existing model deployment,
review the plan, and run `--apply` in an approved environment. Add a local
question file and explicitly authorize smoke-test calls when ready. User
consent and administrator-controlled permissions remain deliberate boundaries.

## Operator-authorized live setup

The curated `genie-agent` / `managed-oauth` setup was subsequently applied to
the operator's configured Foundry project using an existing model deployment.
A dedicated test agent was created and its persisted definition verified.
A second apply successfully reused the same agent version and resources.
Deployment-specific names, endpoints and identifiers remain in ignored local
configuration rather than this customer-neutral report.

Live response inspection identified two compatibility gaps, now fixed:

- Toolbox tools can reference a fully qualified connection resource ID rather
  than its name. Bootstrap compares it to the authoritative connection returned
  for the current project; matching only the basename is not sufficient.
- Non-secret CLI/data-plane connection projections can omit the Entra audience.
  Bootstrap verifies missing audience metadata with a read-only ARM request for
  the authoritative connection ID, without requesting connection secrets.
  A wrong audience or denied management-plane read still fails closed.

| Live setup check | Result |
| --- | --- |
| Operator authentication and existing deployment discovery | PASS |
| Curated-mode connection and Toolbox checks | PASS |
| Agent-to-Toolbox Entra binding and audience verification | PASS |
| Dedicated test-agent creation and persisted definition | PASS |
| Repeated apply preserves the same agent version | PASS |
| Regression suite after live compatibility fixes | PASS: 81 tests |
| OAuth consent and actual Genie tool/query execution | NOT TESTED |
| Genie One live setup or invocation | NOT TESTED |

This establishes provisioning and resource-wiring evidence, not an end-to-end
governed-query result. The next step is a playground invocation or an explicitly
authorized smoke test with a suitable local question file.

## Subsequent runtime discovery check

A playground invocation failed while enumerating the curated Genie tool.
A direct MCP check against the Toolbox reproduced the failure without a model
invocation or data query:

| Check | Result |
| --- | --- |
| Foundry account Resource Health | Available |
| OAuth2 type, documented managed connector name and configured target | Verified through non-secret metadata |
| Toolbox MCP initialization | PASS |
| Direct `tools/list` | FAIL: JSON-RPC `-32007`, with downstream token acquisition reporting `ARA request failed with status BadRequest` |
| Normal consent request | Not surfaced by the failing discovery call |
| Provider consent and successful Genie query | NOT TESTED / not completed |

The immediate failure is downstream token acquisition during discovery.
The checks do not establish the internal ARA broker root cause, and lack of
completed consent alone does not explain why the normal consent flow was not
surfaced. No OAuth scopes, credentials or shared resources were changed during
diagnosis. Follow the [authorization troubleshooting guidance](../troubleshooting.md)
before considering the integration runtime-ready.

## Custom OAuth configuration and continued runtime blocker

With explicit operator approval and Databricks account-administrator sign-in,
a new confidential Databricks OAuth application and separately named Foundry
OAuth2 connection were configured. The application allows `genie` and
`offline_access`, and its callback was replaced with the exact reply URL
generated for that Foundry connection. Provider authorization, token and
refresh URLs were verified against the configured workspace.

The generated secret was transferred in memory to Foundry, not stored in
repository configuration or command arguments. Following separate operator
approval, an in-memory credential inspection verified that the stored client
ID matches the registered application and a nonempty, unmasked secret is
present. This establishes persistence, not secret validity or successful
token exchange. No credential values were printed or persisted locally.

A separate Toolbox and authenticated binding were created, and the dedicated
test agent was updated to a new version referencing them. Original connections,
Toolboxes and agent versions were retained. Active routing was verified using
the server's `@latest` selector with 100% traffic, and regression coverage now
rejects unknown selectors or partial traffic allocation.

| Follow-up check | Result |
| --- | --- |
| Custom app, exact callback, provider URLs and requested scopes | Configured and verified |
| Stored client ID match and secret presence | Verified in memory with operator approval |
| Test-agent configuration and active version routing | Verified |
| Custom OAuth Toolbox discovery | FAIL: ARA token-broker BadRequest; no consent request |
| Direct MCP discovery through Responses, without a Toolbox | FAIL: same ARA error, HTTP 400 |
| Alternative name-based Toolbox connection reference | FAIL: same ARA error; diagnostic version not promoted |
| AppLens diagnostics | Resource type not supported |
| Provider consent, token exchange and governed query | Not verified / not completed |

The direct reproduction establishes that the Toolbox is not the sole cause.
It does not establish an internal broker defect or prove that additional
configuration is unnecessary. The remaining failure needs Foundry-side
investigation using the private request/correlation evidence. That evidence
is kept only in ignored local output; customer identifiers and credentials
are excluded from this report. Further scope broadening, credential rotation,
or shared-resource replacement was not attempted merely to suppress the error.

## Live retest: November 2, 2026

The configured custom-OAuth route was tested again, with the agent test
starting at 20:21 UTC. The dedicated agent's version 2 definition and active
routing were verified before invocation.

| Retest | Result |
| --- | --- |
| Toolbox MCP initialization | PASS: HTTP 200 |
| Toolbox `tools/list` | FAIL: JSON-RPC `-32007`, ARA token-broker BadRequest |
| Agent request to discover available tools | FAIL: HTTP 400, same ARA token-broker error |
| Consent request | Not returned |
| Tool-call approvals | None submitted |
| Governed query | NOT TESTED |

The failure persists after the original setup session; successful provisioning
still does not establish a working integration. Fresh request evidence was
recorded in ignored local diagnostic output for a Foundry support investigation.
No cloud configuration or credentials were changed during this retest.

## OIDC scope control test

On November 2 (local operator time), a separate control was registered with
explicit approval to test the identity-scope difference between the original
API-created application and Databricks' documented UI defaults.

| Setting | Original custom OAuth | Isolated control |
| --- | --- | --- |
| Databricks allowed scopes | `genie offline_access` | `genie openid email profile offline_access` |
| Foundry requested scopes | `genie offline_access` | `genie openid email profile offline_access` |
| Client type | Confidential | Confidential |
| Callback | Original connection's exact callback | Control connection's exact callback |

The new app's allowed scopes, Foundry's requested scopes, and exact callback
registration were verified through non-secret metadata. A separate Toolbox
was created for discovery tests. The original app, connections, Toolboxes,
agent version 2 and local configuration were not changed. No credential
values were printed or saved locally.

Initial direct-MCP and Toolbox discovery tests both returned the same ARA
BadRequest without a consent request. An automatic second test ran at
01:25 UTC on November 3 (November 2 local operator time), at least 31 minutes
after callback configuration to account for the documented OAuth propagation
window.

| Control check | Result |
| --- | --- |
| Five scopes allowed by Databricks and requested by Foundry | PASS: exact match verified |
| Confidential app and exact Foundry callback | PASS: verified |
| Initial direct MCP discovery | FAIL: HTTP 400, ARA BadRequest, no consent request |
| Initial Toolbox discovery | FAIL: JSON-RPC `-32007`, ARA BadRequest, no consent request |
| Post-propagation direct MCP discovery | FAIL: same HTTP 400 / ARA error |
| Post-propagation Toolbox discovery | FAIL: same JSON-RPC `-32007` / ARA error |
| Original agent and local configuration | Unchanged |

No data-tool calls were approved. This control tests the effect of adding
OIDC scopes. Adding `openid`, `email` and `profile` to both allowed and
requested scopes did not resolve the observed failure, including after the
propagation window. Their absence alone is therefore not a sufficient
explanation or fix for this reproduction. This result does not establish
that identity scopes are unnecessary, prove credential validity, or establish
the internal broker root cause.

The control resources were retained separately for diagnosis, with test
timestamps and fresh request IDs only in ignored local output. No existing
application, connection, Toolbox, agent version or local configuration was
repointed to the control. Successful consent, token exchange and governed
queries remain unverified.

## Portal-created comparison connection

The operator then created a connection through the Foundry catalog UI and
reported the same ARA BadRequest shortly after registering its callback.
Read-only inspection confirmed Custom OAuth, the expected workspace
authorization/token/refresh URLs, all five requested scopes, and the new
callback on the five-scope Databricks application.

With explicit approval limited to the new portal-created connection,
an in-memory check confirmed that its client ID matches that application and
a nonempty, unmasked secret is stored. No credential values were displayed
or saved. These checks do not prove secret validity or successful token exchange.

Unlike the direct target used by the scripted connections, the portal-created
catalog connection targets the project's Azure API Management gateway.
This is an additional routing difference, not evidence of malformed user
input. The complete gateway route/backend was not verified. AppLens could
not locate that gateway in its authentication context.

The reported portal error occurred within the possible propagation window
for the newly saved callback. A post-propagation test of this specific portal
connection remains necessary before treating it as equivalent to the
post-propagation scripted-connection failures. No settings or resources were
changed during this inspection, and no data query was approved.

## Live solution test: November 9, 2026

The operator reported that a different Foundry project without the configured
Foundry AI Gateway could use the Databricks connector successfully. This is
an environment-specific observation, not a blanket claim that all gateway
configurations are incompatible, and it concerns Foundry AI Gateway rather
than Databricks Unity Gateway.

Subsequent testing against that project's configured endpoint established:

- The local file still named a model deployment, OAuth connection and agent
  from the earlier project; those resources did not exist in the new project.
- The selected shared Toolbox default version included web search, but its
  version 2 contained only the working curated Genie OAuth connection.
- An existing agent's stored Toolbox URL used the account resource name as
  its hostname. ARM metadata identified a different custom subdomain as the
  authoritative project endpoint. That original agent was not modified.
- Direct discovery against the correct Toolbox endpoint succeeded without
  the earlier ARA error. A constant query reached SQL `SUCCEEDED` and returned
  exactly one row with `connectivity_check = 1`.

The operator then explicitly approved local configuration alignment to the
working OAuth connection and existing model deployment, plus creation of a
separate Genie-only Toolbox, UserEntraToken binding and dedicated test agent.
The original shared Toolbox/default version and original agent version were
verified unchanged after testing.

### Provisioning limitation

The installed `azd` connection extension inferred the wrong ARM account name
from the project's custom hostname and failed with `ParentResourceNotFound`.
The isolated resources were instead provisioned using the SDK and the
authoritative ARM parent ID returned by the existing project connection.
No new model deployment, permission grant, secret read, or shared-resource
replacement was performed. The CLI-based bootstrap provisioning path remains
blocked for this resource-name/custom-subdomain layout; this workaround is
not yet an automatic bootstrap feature.

### Verified full agent test

The isolated agent used the existing model, called Genie through its pinned
Toolbox and OAuth connection, and polled the pending query to completion.
The test inspected the actual query attachment, SQL status, column name and
row value instead of trusting a textual answer:

```sql
SELECT 1 AS connectivity_check
```

Result: SQL `SUCCEEDED`, exactly one row, `connectivity_check = 1`.
No business tables or business rows were requested. The first agent attempt
returned a completed tool response without a query attachment; it was
explicitly classified NOT VERIFIED. A subsequent stricter request yielded
the verified execution evidence above.

Live testing also exposed and fixed smoke-helper compatibility defects:

- Omit `previous_response_id` on the first request rather than sending null.
- Inspect concatenated JSON blocks and the `structuredResponse` envelope.
- Recognize uppercase curated-query failures and reject nonterminal statuses
  as proof of completed queries.

| Check | Result |
| --- | --- |
| Full offline suite after fixes | PASS: 85 tests |
| Python compilation and changed-source diagnostics | PASS |
| Existing Genie-only Toolbox discovery | PASS |
| Direct Toolbox -> OAuth -> Genie constant SQL query | PASS: exact SQL/result verified |
| Isolated agent -> Toolbox -> OAuth -> Genie constant SQL query | PASS: exact SQL/result verified |
| Existing shared agent/Toolbox preserved | PASS |
| CLI bootstrap provisioning with differing account name/subdomain | FAIL: `ParentResourceNotFound`; SDK/ARM provisioning used instead |
| Business-data permissions, cross-user isolation and effective identity auditing | NOT TESTED |
| Fresh consent, refresh/revocation and negative authorization tests | NOT TESTED |
| Genie One runtime | NOT TESTED |

This is successful end-to-end **curated-mode connectivity**, not production
certification or proof of table-level authorization. Resource names, response
handles and machine-readable test evidence remain in ignored local output.
The new test agent can be exercised in the Foundry playground; the original
agent's hostname mismatch and the CLI provisioning limitation remain separate
follow-up items.

### Repeat verification later on November 9

The offline suite again passed all 85 tests. The local configuration had been
changed to select the original shared test agent, whose saved Toolbox URL
still used the account resource name rather than the authoritative custom
hostname. That agent did not pass the wiring preflight and was not invoked.

Using a process-only agent-name override, the previously verified isolated
agent was retested without changing local configuration or cloud resources.
It called the Genie query tool, polled `ASKING_AI` to `COMPLETED`, and returned
a SQL `SUCCEEDED` result for `SELECT 1 AS connectivity_check` with exactly
one row containing `1`. The repeated end-to-end connectivity test passed;
this result applies to the isolated agent, not the differently configured
original agent. No business data was requested.

## Existing-agent repair and non-provisioning tests: November 11, 2026

The operator approved correcting the existing portal-created agent and adding
a test path that does not provision resources. The current agent was
re-inspected before changing it:

- Version 5 referenced a real Genie-only Toolbox, but used a resource-name-
  derived hostname rather than the authoritative project custom subdomain.
- Version 6 changed only the MCP `server_url`; the persisted definition was
  compared with the original to verify instructions, model, tools and approval
  settings were otherwise preserved. Version 5 remained intact.
- Direct discovery at the corrected Toolbox URL succeeded, but agent-mediated
  invocation still returned HTTP 400 `tool_user_error`. No ARA failure was
  reported for that invocation.
- With **separate operator approval**, a UserEntraToken project connection was
  created for that exact pinned Toolbox URL, with audience
  `https://ai.azure.com`. Version 7 changed only `project_connection_id`
  relative to version 6. The downstream Databricks OAuth connection, Toolbox,
  model and instructions were preserved.

The new `test-agent` command reads the existing saved agent and its pinned
Toolbox version; it does not use bootstrap ownership metadata or create/update
resources. It uses the saved model, server label and optional connection
reference, so `FOUNDRY_MODEL_DEPLOYMENT` and
`FOUNDRY_TOOLBOX_CONNECTION_NAME` are not needed for this command. That does
not imply a Toolbox authentication connection is unnecessary at runtime:
in this explicit MCP attachment, the URL-only repair failed and adding the
authenticated binding was followed by a successful test.

The local Toolbox setting was aligned to the Toolbox actually used by the
requested agent. No alternate test agent was substituted. The requested
agent's active version 7 was tested using the non-provisioning command.
Evidence inspection confirmed `SELECT 1 AS connectivity_check`, SQL status
`SUCCEEDED`, exactly one result row and value `1`. A pending query was polled
to `COMPLETED`; an agent's textual claim alone was not counted as proof.
No business tables or business rows were requested.

| Validation | Result |
| --- | --- |
| URL-only new version, other definition fields preserved | PASS |
| Prior agent version retained | PASS |
| Separate approved Toolbox access binding, target/type/audience verified | PASS |
| Existing-agent test through saved model, Toolbox, OAuth and Genie | PASS |
| Actual constant SQL and exact result | PASS |
| Non-provisioning command regression coverage | PASS; no create/update/delete operations used |
| Full offline suite | PASS: 97 tests |
| Static type-check | PASS: Pyright with Python 3.10 language compatibility |
| Editor diagnostic service | Unavailable: timed out; local type-check used instead |
| Python compilation and package build | PASS |
| Cross-user isolation, business-data permissions and fresh consent | NOT TESTED by this constant-query check |

Use [the existing-agent command](../bootstrap.md#test-an-existing-agent-without-provisioning)
for subsequent tests rather than `bootstrap --apply`. The URL repair and
binding attachment were separately authorized administrative operations,
not side effects of `test-agent`.
