# Troubleshooting

## Managed MCP Servers is unavailable

Enable the preview in the Databricks workspace settings. If organizational
policy blocks previews, stop and use an approved alternative.

## Connection creation is unauthorized

Confirm the operator is authenticated with `azd auth login` and has the
current Foundry role required to manage project connections.

## The managed connector is unavailable

Update `azd` and its Foundry extensions. If the connector is unavailable in
the tenant or region, follow [custom-oauth.md](custom-oauth.md).

## `CONSENT_REQUIRED` is returned

This is expected on the first OAuth invocation. Open the returned consent URL,
sign in to Databricks, approve access, and retry.

## Consent succeeds but the tool call is denied

Confirm the signed-in Databricks user can use the Genie Agent and access its
underlying governed data. OAuth success does not bypass Unity Catalog.

## The wrong Genie Agent is called

Verify `DATABRICKS_GENIE_SPACE_ID`, then rerun setup with:

```powershell
.\scripts\setup.ps1 -ReplaceConnection
```

The Toolbox references the connection by name, so replacing the connection
updates its target without creating a new Toolbox.

## The Toolbox already exists

The setup preserves existing Toolbox versions. Choose a new
`FOUNDRY_TOOLBOX_NAME` if the existing Toolbox is unrelated. Do not delete or
mutate a shared Toolbox without checking its consumers.

## OAuth changes do not work immediately

Custom Databricks OAuth application updates can take up to 30 minutes to
propagate. Managed connector availability can also vary by tenant and region.

