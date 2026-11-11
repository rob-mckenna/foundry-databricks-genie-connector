# Microsoft Foundry to Azure Databricks Genie

Reference implementation for sharing Databricks analytics
tools across Microsoft Foundry agents through a reusable **Toolbox** and a
reusable **OAuth project connection**. Authentication stays in Foundry; data
authorization stays in Databricks.

## Choose an integration mode

| Mode | Use when | Databricks endpoint | Status |
| --- | --- | --- | --- |
| `genie-one` | You need workspace-wide analytics grounded in Genie Ontology | `/ai-gateway/mcp-services/system.ai.genie_one_mcp?o=<workspace-id>` | Genie One MCP is GA |
| `genie-agent` | You need one curated Genie Agent's data, instructions and examples | `/api/2.0/mcp/genie/<space-id>` | Genie Agent MCP is Public Preview |

```text
Foundry agents (multiple consumers)
    |
    v
Reusable Foundry Toolbox
    |
    v
OAuth project connection (per-user provider authorization)
    |
    +-- genie-one --> Unity Gateway --> system.ai.genie_one_mcp
    |                                  --> Genie One / Genie Ontology
    |
    +-- genie-agent ---------------------> selected curated Genie Agent
                                                |
                   Unity Catalog-governed data <-+
                   (applies to BOTH modes)
```

The modes are not interchangeable. Curated Genie Agent calls **bypass Unity
Gateway**. Genie One has an asynchronous ask/poll workflow and can continue a
conversation; the curated MCP interface does not forward conversation history.

> [!IMPORTANT]
> Genie One MCP being GA does not make every component of this integration GA.
> See the [feature-specific lifecycle and source register](docs/architecture.md).
> Neither integration mode has been end-to-end certified by this repository.
> Follow [validation](docs/validation.md) in your own environment.

A live **curated-mode connectivity test** has passed through agent, Toolbox,
OAuth and Genie: `SELECT 1 AS connectivity_check` returned exactly `1`.
This does not certify business-data authorization or Genie One.
See the [live test results and CLI provisioning limitation](docs/evidence/modernization-report.md#live-solution-test-november-9-2026).

## Authentication choices

- `managed-oauth` (default): setup creates/reuses the documented
  `foundrydatabricksmcp` connector for **genie-agent**. No client secret is needed.
- `existing-oauth`: setup references an OAuth connection you have already
  provisioned in Foundry. Supported for both modes; setup never replaces it.
  Use [custom OAuth setup](docs/custom-oauth.md) to create it without putting
  secrets in repository files or command arguments.

**Genie One requires `existing-oauth`.** The managed connector's support for
the Gateway endpoint and `ai-gateway` scope has not been verified. The scripts
reject that unverified combination rather than assuming an endpoint swap works.
Foundry still manages the tokens when you supply your own OAuth application.

## Prerequisites

- An existing Foundry project. Connection operators need **Foundry Project
  Manager**; see [authorization](docs/security.md) for Toolbox developers,
  runtime agents and end users.
- Python 3.10 or later and Azure Developer CLI (`azd` 1.27.1 or later) with
  the Foundry connection and Toolbox extensions.
- An Azure Databricks workspace and users with the required access:
  - **Genie One:** workspace ID, configured Genie One, Gateway service grants,
    underlying data permissions, and a compatible OAuth connection.
  - **Genie Agent:** workspace **Managed MCP Servers** preview enabled,
    an existing Genie Agent/space ID, agent access and data permissions.
- Network connectivity from the Foundry runtime to the Databricks endpoint.
  Local CLI connectivity alone does not establish this.

Install/update tooling explicitly, then sign in:

```powershell
azd extension install microsoft.foundry
azd extension update --all
azd auth login
```

Normal setup does not install tooling, create projects/workspaces/agents, grant
permissions, or perform interactive consent. The optional bootstrap below
adds a dedicated test agent and guides user consent without bypassing it.

## Prepare Azure Databricks first

This repository does not provision an Azure Databricks workspace, its data or
a Genie Agent. Complete the applicable Databricks setup before running this
connector:

1. [Create an Azure Databricks workspace](https://learn.microsoft.com/azure/databricks/admin/workspace/).
2. [Create, configure and share a Genie Agent](https://learn.microsoft.com/azure/databricks/genie-agents/set-up),
   including its Unity Catalog data and SQL warehouse.
3. For `genie-agent`, [enable and configure the Genie Agent MCP server](https://learn.microsoft.com/azure/databricks/agents/mcp-tools/genie-agent),
   then copy the Genie space ID from the agent's settings.

For `genie-one`, follow the [Genie One MCP documentation](https://learn.microsoft.com/azure/databricks/agents/mcp-tools/genie-mcp)
and the repository's [custom OAuth setup](docs/custom-oauth.md) instead of
creating a space-specific Genie Agent connection.

## Quick start

1. Copy [.env.example](.env.example) to `.env`.
2. Configure the selected mode using the [configuration table](docs/manual-setup.md).
   Defaults preserve the original curated-agent scenario.
3. For `existing-oauth`, provision the connection first.
4. Validate offline, then run setup for your shell.

PowerShell, from the repository root:

```powershell
Copy-Item .env.example .env
# Edit .env before continuing.
$env:PYTHONPATH = "$PWD\src"
python -m foundry_databricks_genie.cli validate
.\scripts\setup.ps1
```

Bash:

```bash
cp .env.example .env
# Edit .env before continuing.
export PYTHONPATH="$PWD/src"
python -m foundry_databricks_genie.cli validate
bash ./scripts/setup.sh
```

Setup prints the Toolbox consumer endpoint. It preserves matching resources
and checks their connection references. Failed inspection is an error, not
evidence that a resource is missing. Setup does **not** invoke an agent or
prove that OAuth, Gateway authorization or a query succeeds.

Use distinct names for different modes/targets. The explicit managed
replacement options (`-ReplaceConnection` / `--replace-connection`) affect
**every consumer** of that connection. See [migration](docs/migration.md).

## Complete user consent and verify

Attach the Toolbox to an agent and ask an authorized data question. Follow
Foundry's consent link, sign in to Databricks, approve access, and resume/retry
the request. Consent is per user, connection and Foundry project, not a shared
Databricks login for all agents.

Follow [the full validation procedure](docs/validation.md), including two
users with different permissions. Successful setup or successful consent
alone is not an end-to-end test.

## Automate the test-agent setup

The optional [guided bootstrap](docs/bootstrap.md) creates a dedicated prompt
agent, wires authenticated access to a pinned Toolbox version, and can run a
consent-aware smoke test. It uses an existing model deployment and never
replaces unrelated agents.

```powershell
python -m pip install -e ".[bootstrap]"
# Add FOUNDRY_TEST_AGENT_NAME and FOUNDRY_MODEL_DEPLOYMENT to your local .env.
.\scripts\setup.ps1 -Bootstrap
# Review the plan, then explicitly apply it:
.\scripts\setup.ps1 -Bootstrap -Apply
```

For a complete smoke test, add `-QuestionFile <local-question-file>` and
`-ApproveTools`. User OAuth consent remains interactive. With
`-NonInteractive`, missing consent returns an explicit needs-consent status.
Read the [bootstrap guide](docs/bootstrap.md) before approving tool execution.

## Test an existing agent without provisioning

For an agent created in the portal or elsewhere, use `test-agent`, not
`bootstrap`. Set `FOUNDRY_TEST_AGENT_NAME` to that agent and
`FOUNDRY_TOOLBOX_NAME` / `FOUNDRY_CONNECTION_NAME` to its actual Toolbox and
downstream Genie OAuth connection. The saved agent supplies its model,
pinned Toolbox version, server label and any existing authentication binding.

```powershell
.\.venv\Scripts\python.exe -m foundry_databricks_genie.cli test-agent `
  --env-file .env `
  --question-file .generated\connectivity-question.txt `
  --approve-tools --non-interactive
```

Create the UTF-8 question file locally; for connectivity testing, request only
`SELECT 1 AS connectivity_check` through Genie and polling until completion.
The [existing-agent testing guide](docs/bootstrap.md#test-an-existing-agent-without-provisioning)
explains the checks and permissions. This command never creates/updates
agents, Toolboxes, connections or roles, but **does invoke tools** and can incur
charges. Use only approved read-only questions for read-only data tests.
`FOUNDRY_TOOLBOX_CONNECTION_NAME` and `FOUNDRY_MODEL_DEPLOYMENT` are not required
by this command; they remain bootstrap settings.

## Offline tests

```powershell
$env:PYTHONPATH = "$PWD\src"
python -m unittest discover -s tests -v
```

Tests use synthetic data and mocked `azd` responses. They do not authenticate
to Azure or Databricks. Git is required for repository hygiene checks.
Install `.[bootstrap]` to include the optional SDK contract tests; otherwise
those tests are skipped. CI installs the extra.

## Documentation

- [Architecture, assessment, lifecycle and authoritative sources](docs/architecture.md)
- [Configuration and manual setup](docs/manual-setup.md)
- [Guided test-agent bootstrap](docs/bootstrap.md)
- [Custom OAuth and scopes](docs/custom-oauth.md)
- [Authorization and security](docs/security.md)
- [Migration from the original implementation](docs/migration.md)
- [Validation and evidence](docs/validation.md)
- [Historical implementation evidence](docs/evidence/modernization-report.md)
- [Troubleshooting](docs/troubleshooting.md)
