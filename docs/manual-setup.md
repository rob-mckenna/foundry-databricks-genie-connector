# Manual setup and verification

Use this path when scripts are not permitted or when validating each operation
with a platform administrator.

## 1. Collect non-secret values

- Foundry project endpoint
- Databricks workspace root URL
- Genie Agent space ID
- Desired project connection name
- Desired Toolbox name

The Genie MCP endpoint is:

```text
https://<workspace-host>/api/2.0/mcp/genie/<genie-space-id>
```

## 2. Create the project connection

```text
azd ai connection create <connection-name> \
  --kind remote-tool \
  --target <genie-mcp-endpoint> \
  --auth-type oauth2 \
  --connector-name foundrydatabricksmcp \
  --project-endpoint <foundry-project-endpoint>
```

This command uses the Foundry-managed Databricks OAuth connector and does not
require a client secret.

## 3. Create the Toolbox

Create `toolbox.yaml`:

```yaml
description: Azure Databricks Genie tools exposed through a managed Foundry Toolbox.
connections:
  - name: <connection-name>
```

Create the Toolbox:

```text
azd ai toolbox create <toolbox-name> \
  --from-file toolbox.yaml \
  --project-endpoint <foundry-project-endpoint>
```

## 4. Attach and consent

1. In Foundry, open **Build > Tools**.
2. Select the Toolbox and choose **Use in an agent**, or attach it to an
   existing agent.
3. Ask a question that requires the Genie tool.
4. Open the consent link from the `CONSENT_REQUIRED` response.
5. Sign in to Databricks and approve access.
6. Retry the question.

## 5. Verify

Confirm that:

- the Toolbox is visible in Foundry;
- the agent discovers the Genie MCP tool;
- the first invocation requests consent;
- the post-consent invocation succeeds;
- the response is limited to data the signed-in user can access.

Use a neutral verification prompt that is valid for the configured Genie
Agent. Do not add customer data or expected answers to this repository.

## Cleanup

Review each resource before deleting it:

```text
azd ai toolbox delete <toolbox-name> --project-endpoint <project-endpoint>
azd ai connection delete <connection-name> --project-endpoint <project-endpoint>
```

Deleting shared resources can break other agents. The repository intentionally
does not automate cleanup.

