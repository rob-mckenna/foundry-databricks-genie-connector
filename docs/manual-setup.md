# Configuration and manual setup

## Non-secret configuration

Copy `.env.example` to `.env`. Shell environment values override the file,
including mode selection. A file is still required. Quoted values and UTF-8
files with/without BOM are supported; shell expansion is not performed.

| Variable | Requirement |
| --- | --- |
| `FOUNDRY_PROJECT_ENDPOINT` | HTTPS project endpoint, ending `/api/projects/<project>` |
| `DATABRICKS_WORKSPACE_HOST` | HTTPS workspace root, without credentials, query, fragment or path |
| `DATABRICKS_INTEGRATION_MODE` | `genie-agent` (default if omitted) or `genie-one` |
| `DATABRICKS_GENIE_SPACE_ID` | Required only for `genie-agent`; remove/empty for `genie-one` |
| `DATABRICKS_WORKSPACE_ID` | Positive decimal ID required only for `genie-one`; remove/empty for `genie-agent` |
| `FOUNDRY_CONNECTION_MODE` | `managed-oauth` (default) or `existing-oauth`; Genie One requires `existing-oauth` |
| `FOUNDRY_CONNECTION_NAME` | Project connection name; must already exist for `existing-oauth` |
| `FOUNDRY_TOOLBOX_NAME` | Toolbox name; choose new names for unrelated targets |

Resource names use letters, numbers, underscores or hyphens, start with an
alphanumeric character, and have a maximum of 80 characters. Identifiers and
URLs are deployment metadata: they belong in local configuration, not Git.
Inactive identifiers are rejected rather than silently ignored.

Genie One example:

```dotenv
FOUNDRY_PROJECT_ENDPOINT=https://<foundry-account>.services.ai.azure.com/api/projects/<foundry-project>
DATABRICKS_WORKSPACE_HOST=https://<databricks-workspace>.azuredatabricks.net
DATABRICKS_INTEGRATION_MODE=genie-one
DATABRICKS_WORKSPACE_ID=<workspace-id>
FOUNDRY_CONNECTION_MODE=existing-oauth
FOUNDRY_CONNECTION_NAME=databricks-genie-one
FOUNDRY_TOOLBOX_NAME=databricks-genie-one-toolbox
```

Do not add credentials to this file. Use the actual workspace ID, not a tenant,
subscription, account or Genie space ID, and do not infer it from a hostname.

## Offline inspection

From the repository root in PowerShell:

```powershell
$env:PYTHONPATH = "$PWD\src"
python -m foundry_databricks_genie.cli validate --env-file .env
python -m foundry_databricks_genie.cli endpoint --env-file .env
python -m foundry_databricks_genie.cli render-toolbox --env-file .env --output .generated\toolbox.yaml
```

`config` prints the non-secret configuration as JSON, including the target,
required scopes and Toolbox consumer URL. Treat that output as private
deployment metadata. None of these commands authenticates or checks grants.
`preflight` checks that `azd` is available, not login or extension compatibility.

## Create or select the connection

For **Genie One**, first follow [custom OAuth setup](custom-oauth.md).
There is intentionally no automated managed-connector command for this mode.

For **curated Genie Agent with managed OAuth**, the documented command is:

```text
azd ai connection create <connection-name> --kind remote-tool --target https://<workspace-hostname>/api/2.0/mcp/genie/<space-id> --auth-type oauth2 --connector-name foundrydatabricksmcp --project-endpoint <project-endpoint>
```

The selected endpoint and provider must be available in your deployment.
Do not copy another provider's catalog metadata (for example GitHub's) into a
Databricks connection. Catalog-specific metadata/behavior must be verified
against the actual connector if your environment requires it.

For either mode with **existing OAuth**, use the exact connection name and
target. Setup never replaces or silently reconfigures this connection.

## Create the Toolbox

Render the file with the offline command above, or use this definition:

```yaml
description: Azure Databricks Genie tools exposed through a managed Foundry Toolbox.
connections:
  - name: <connection-name>
```

```text
azd ai toolbox create <toolbox-name> --from-file <toolbox-file> --project-endpoint <project-endpoint>
```

Alternatively, use either repository setup script or the shared command:

```powershell
python -m foundry_databricks_genie.cli setup --env-file .env
```

The direct command's output file defaults to `.generated/toolbox.yaml` in the
current directory. Shell wrappers always use the repository's generated
directory. PowerShell accepts `-EnvFile`; Bash accepts `ENV_FILE`.

Setup checks complete resource lists before inferring absence. It checks
existing Toolbox connections before replacing a managed connection, verifies
new resource references, and does not save raw connection responses.
Unknown CLI schemas fail explicitly. Scope fields that are not exposed are
reported as unverified. No automatic rollback deletes shared resources after
a partial failure; inspect state before retrying.

## Attach, consent and test

For an existing agent, use the [non-provisioning test-agent command](bootstrap.md#test-an-existing-agent-without-provisioning).
It follows the saved agent's explicit Toolbox version and optional binding;
it does not require `FOUNDRY_TOOLBOX_CONNECTION_NAME` or bootstrap ownership.

To automate this phase, use [guided bootstrap](bootstrap.md). It requires a
dedicated test-agent name, an existing model deployment, and the optional
Python SDK extra. The default bootstrap command is plan-only.

Use the printed Toolbox consumer endpoint or Foundry's **Use in an agent**
experience. Test a version-specific endpoint before changing a shared default.
Follow [validation](validation.md), not just a first successful consent.

## Cleanup

First inspect all consumers and resource ownership. Only then, if removal is
intended, use the CLI's explicit deletion flags:

```text
azd ai toolbox delete <toolbox-name> --project-endpoint <project-endpoint> --force --no-prompt
azd ai connection delete <connection-name> --project-endpoint <project-endpoint> --force --no-prompt
```

This repository does not automate deletion or OAuth application cleanup.
