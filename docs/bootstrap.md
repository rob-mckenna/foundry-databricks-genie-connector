# Guided test-agent bootstrap

This optional workflow automates connection/Toolbox setup, creates a dedicated
prompt agent using an **existing model deployment**, and optionally runs a
consent-aware smoke test. It does not create projects, workspaces, model
deployments, custom OAuth applications, or role assignments.

The normal setup commands retain their existing behavior. Bootstrap is
**plan-only by default**; `--apply` is required for cloud operations.
To test a portal-created agent without provisioning or bootstrap ownership
requirements, use [test-agent](#test-an-existing-agent-without-provisioning).

> **Known CLI resolution limitation:** the installed connection extension was
> observed inferring the ARM account name from the project hostname. When the
> account resource name differs from its custom subdomain, this returned
> `ParentResourceNotFound` even though SDK project access worked. The bootstrap
> stops rather than overwriting resources or changing the endpoint. The live
> validation used the authoritative ARM resource ID and SDK for isolated
> provisioning; that is not an automatic fallback in the bootstrap command.
> See [troubleshooting](troubleshooting.md#parentresourcenotfound-during-connection-list).

## What is automated

```text
Validate local settings and optional question file
  -> show proposed operations
  -> [explicit --apply]
  -> verify model deployment and existing agent ownership
  -> create/reuse Databricks OAuth connection and Toolbox
  -> pin the Toolbox's current default version
  -> create/reuse an agent-to-Toolbox UserEntraToken connection
  -> create/reuse the dedicated prompt agent
  -> print agent/version and Foundry portal handoff
  -> [optional question file]
  -> invoke agent -> consent if required -> tool approval -> inspect results
```

The authenticated route is:

```text
Dedicated prompt agent
  -> UserEntraToken project connection (audience: https://ai.azure.com)
  -> version-specific Toolbox MCP endpoint
  -> existing Databricks OAuth connection
  -> Genie MCP
```

The extra Entra connection authenticates the **Foundry-to-Toolbox** hop. It is
not a replacement for provider OAuth and does not forward a Foundry token to
Databricks. This follows Microsoft's
[prompt-agent Toolbox attachment example](https://learn.microsoft.com/azure/foundry/agents/how-to/tools/connectors#add-a-managed-mcp-server).
Toolbox integration with prompt agents is preview; verify availability and
permissions in your project.

## 1. Install the optional dependencies and sign in

The base package remains dependency-free. Bootstrap's optional SDK extra
supports Python 3.10 or later:

```powershell
python -m pip install -e ".[bootstrap]"
azd auth login
```

Use your intended **user identity** for per-user testing, not an unattended
service principal. The SDK uses `AzureDeveloperCliCredential` so SDK and
existing `azd` setup operations use the same login source. Missing/expired
authentication is an explicit error; the workflow does not select another
identity or install/update tools automatically.

Bootstrap currently supports public-Azure project hostnames under
`*.services.ai.azure.com` on HTTPS/443, including those resolved through
private DNS. Custom hosts and other clouds are rejected before acquiring
tokens; their token audiences and endpoints need a separately verified
implementation.

For editor diagnostics, select a Python environment containing the bootstrap
extra. Installing into a terminal interpreter does not change VS Code's
selected interpreter.

## 2. Add non-secret bootstrap settings

In the ignored environment file, add:

```dotenv
FOUNDRY_TEST_AGENT_NAME=databricks-genie-test
FOUNDRY_MODEL_DEPLOYMENT=<existing-model-deployment-name>
```

`FOUNDRY_MODEL_DEPLOYMENT` is a deployment name, not merely a model catalog
name. There is no automatic model selection or deployment.

The agent-to-Toolbox connection defaults to `<test-agent-name>-toolbox`.
Override it with `FOUNDRY_TOOLBOX_CONNECTION_NAME` if necessary. It must differ
from the Databricks OAuth connection name. Agent and connection names follow
the existing alphanumeric/underscore/hyphen, maximum-80-character validation.
Existing model deployment names may also contain periods.

Both integration modes are supported. Genie One still requires a separately
provisioned compatible OAuth connection (`existing-oauth`); this workflow does
not remove that safety gate.

## 3. Review the plan

PowerShell:

```powershell
.\scripts\setup.ps1 -Bootstrap
```

Bash:

```bash
bash ./scripts/setup.sh --bootstrap
```

Or, after package installation:

```text
foundry-databricks-genie bootstrap --env-file .env
```

Planning validates local configuration only: no cloud calls, dependency
installation, browser launch or generated-file writes. It does not establish
permissions, resource existence or model compatibility.

## 4. Apply, with or without a smoke test

Provision just the test agent and supporting resources:

```powershell
.\scripts\setup.ps1 -Bootstrap -Apply
```

For a smoke test, create a small UTF-8 question file in an ignored location,
such as `.generated/smoke-question.txt`. Choose a question appropriate to your
synthetic/non-production data. Do not commit the question or use credentials
as input. The limit is 32 KiB.

PowerShell:

```powershell
.\scripts\setup.ps1 -Bootstrap -Apply -QuestionFile .generated\smoke-question.txt -ApproveTools
```

Bash:

```bash
bash ./scripts/setup.sh --bootstrap --apply \
  --question-file .generated/smoke-question.txt --approve-tools
```

`--approve-tools` / `-ApproveTools` explicitly authorizes MCP calls made by
this smoke test. The saved agent still has `require_approval="always"`; the
flag submits approval responses for the test only. If you need to inspect
individual arguments before approval, omit the flag and use the playground.
The Toolbox must contain **only the configured Genie MCP connection**, with
no additional tools or skills; bootstrap rejects a broader shared Toolbox.
Both connection-name references and fully qualified connection IDs are
accepted. Full IDs must match the authoritative connection returned for the
current project; matching only the final name is insufficient.

If the CLI omits the agent-to-Toolbox connection's audience, bootstrap verifies
it with a read-only ARM request for that connection's authoritative resource
ID. This requires management-plane connection read access. It never requests
connection secrets or treats a missing audience as valid.

Model invocations and Databricks queries can incur charges. The question,
tool results and conversation can be stored in Foundry. They are not printed
or persisted by this local helper; review platform retention and tracing
policies before testing sensitive data.

## Consent and non-interactive operation

For an `oauth_consent_request`, an interactive terminal displays the HTTPS
host and asks before opening the browser. The full consent link is not
printed or saved. Sign in, approve access, and return to the terminal to
resume the previous response. Browser launch/closure is **not** counted as
successful consent; a subsequent tool result is required.

`--non-interactive` / `-NonInteractive`, or a redirected terminal, never opens
a browser or waits for input. Missing consent or tool approval returns exit
code 3. Complete authorization in the Foundry playground under the same user
and retry. The workflow never bypasses MFA, consent or administrator approval.
It does not persist response IDs; an interrupted run can be retried as a new
question after reviewing any ongoing query.

## Reuse and safety

- An existing agent must carry this workflow's ownership metadata and match
  the model, instructions and complete Toolbox tool definition. Otherwise
  choose a new name. No update, replacement or deletion is performed.
- Existing Toolbox default-version changes cause an agent-definition mismatch
  rather than silently switching the test agent. Use a new test-agent name
  and binding name to test the new version.
- The default Toolbox version is pinned in the agent-to-Toolbox connection.
  Bootstrap does not promote Toolbox versions.
- The current agent endpoint is used through the supported SDK. Before and
  after a smoke test, its latest version and single-version routing are
  checked. A 100% route to the verified version or the server's `@latest`
  selector is accepted. Unknown/mixed routing fails verification; it is not guessed.
- Do not run concurrent bootstraps or edit the test agent/connection while a
  test runs. Version creation is not a distributed resource lock.
- Cloud failures/timeouts stop the flow. There is no automatic mutation retry
  or destructive rollback. Inspect existing resource/query state before retrying.
- Requests are bounded to 12 Responses API calls with a 120-second request
  timeout and 4,096 output-token limit per call. Consent waiting is interactive.
  Exceeding a limit is not success and does not cancel remote work.

## Results and playground handoff

| Exit code | Meaning |
| --- | --- |
| `0` | Plan succeeded, provisioning succeeded without a requested test, or requested smoke evidence was observed; read the printed status to distinguish them |
| `2` | Configuration, dependency, provisioning or API failure |
| `3` | User consent or tool approval is required/not completed |
| `4` | Smoke test failed or did not provide sufficient evidence |
| `130` | Interrupted; inspect remote state before retrying |

A successful smoke test requires a completed MCP call through the configured
Toolbox **and** a final agent answer. Tool discovery or an LLM-only answer
cannot pass. Machine-readable MCP errors fail. Genie One additionally requires
a structured `completed` result from `genie_poll_response`; an asynchronous
query merely starting is insufficient. Unknown result shapes fail verification
rather than being treated as completed Genie One queries.
For curated Genie, an exposed nonterminal query status such as
`PENDING_WAREHOUSE` or `ASKING_AI` cannot pass as query completion. Foundry's
concatenated JSON output blocks and `structuredResponse` wrapper are inspected
without printing their values.

This is **transport/execution evidence**, not a correctness oracle: a completed
curated MCP call can still return no rows or explain insufficient access.
Answer correctness, actual identity, data permissions, refresh and isolation
require the [full live validation procedure](validation.md).

The helper prints `https://ai.azure.com/`, the agent name and version. Open the
configured project and select that agent in the playground. It deliberately
does not guess a project-specific portal URL from a data-plane endpoint.

## Test an existing agent without provisioning

`test-agent` is a separate, non-provisioning path. It reads the saved agent,
validates its pinned Toolbox and downstream Genie connection, then invokes
that agent. It does not create, update, replace, promote or delete resources.
It does not require the bootstrap's ownership marker or rewrite instructions.

Configure:

- The normal project, Databricks endpoint/mode and downstream OAuth settings.
- `FOUNDRY_TEST_AGENT_NAME`: the existing agent to invoke.
- `FOUNDRY_TOOLBOX_NAME`: the Toolbox actually referenced by that saved agent.
- `FOUNDRY_CONNECTION_NAME`: its downstream Databricks OAuth connection.

This command **ignores** `FOUNDRY_MODEL_DEPLOYMENT` and
`FOUNDRY_TOOLBOX_CONNECTION_NAME`. It uses the model and optional
`project_connection_id` stored on the agent. A separate Toolbox-access
connection is not created or inferred merely from an environment variable.
If the agent already references a connection, its exact identity and target
are checked. If it has no reference, testing is allowed without one; whether
that route authenticates successfully is a runtime question, not assumed.

The agent must have one Toolbox MCP tool, without additional tools, skills,
custom headers or a harness. The pinned Toolbox version must contain only
the configured Genie OAuth tool. Its default version may differ; `test-agent`
uses the explicitly saved version rather than promoting or following a default.
The saved Toolbox URL must use the authoritative project hostname, the
configured Toolbox name, an explicit version, and `api-version=v1`.
Agent version/routing and inspected wiring are rechecked after invocation.

Install the same optional SDK extra and use the same `azd` user login as
bootstrap. Run:

```powershell
.\.venv\Scripts\python.exe -m foundry_databricks_genie.cli test-agent `
  --env-file .env `
  --question-file .generated\connectivity-question.txt `
  --approve-tools --non-interactive
```

The question file is required. Do not put credentials in it. The saved model
and tools can run immediately: there is no plan/apply stage for this command.
If the saved agent permits automatic tool execution, `--approve-tools` is
required before invocation. Otherwise tool approval requests are surfaced
unless this flag is provided. The saved approval policy is never changed.
Consent is handled by the same bounded smoke-test flow, with the same exit
codes. Non-interactive missing consent returns code 3.

"Non-provisioning" is **not** a promise that arbitrary questions are read-only:
the invocation can use tools, incur charges and retain conversation data in
Foundry. For a read-only connectivity test, request only
`SELECT 1 AS connectivity_check`, prohibit business-table access, and require
Genie to finish its query before returning an answer. Inspect actual query
attachments to establish exact SQL/result correctness; generic smoke success
only establishes tool execution plus a final answer.

### Correcting a saved Toolbox URL

Editing `.env` does not edit the remote agent. Correct the URL by saving a
**new agent version** whose MCP tool points to:

```text
<authoritative-project-endpoint>/toolboxes/<actual-toolbox-name>/versions/<pinned-version>/mcp?api-version=v1
```

Use the project endpoint returned by Foundry/ARM, not a hostname constructed
from the account's resource name. Preserve the existing definition and change
only `tools[n].server_url`, then verify the persisted definition and active
version. Keep the prior version for rollback; do not mutate a shared Toolbox
or promote its default to repair an agent URL.

If direct Toolbox discovery works but agent-mediated access still fails, the
agent may also need the explicit UserEntraToken binding described earlier.
Create/attach it only as a separate approved configuration change. It is an
authentication resource, not another Toolbox. `test-agent` itself will not
perform that repair.

Sources:
- [Prompt agents](https://learn.microsoft.com/azure/foundry/agents/concepts/prompt-agents)
- [Current prompt-agent invocation](https://learn.microsoft.com/azure/foundry/agents/quickstarts/prompt-agent)
- [Toolbox attachment](https://learn.microsoft.com/azure/foundry/agents/how-to/tools/connectors#add-a-managed-mcp-server)
- [OAuth consent and continuation](https://learn.microsoft.com/azure/foundry/agents/how-to/mcp-authentication)
- [Prompt-agent Toolbox preview](https://learn.microsoft.com/azure/foundry/how-to/develop/create-prompt-agent-visual-studio-code#use-a-toolbox-preview)
