# Migration from the original connector

## Existing curated Genie Agent users

No endpoint or identifier change is required. If the new mode settings are
omitted, setup still selects:

```dotenv
DATABRICKS_INTEGRATION_MODE=genie-agent
FOUNDRY_CONNECTION_MODE=managed-oauth
```

Keep the existing space ID and resource names if the target is unchanged.
The `/api/2.0/mcp/genie/<space-id>` endpoint remains documented in Public
Preview. "Genie Agent" is the current name for what was formerly a Genie Space;
the API/configuration still uses a space ID.

## Opt in to Genie One

1. Review the functional difference: Genie One uses workspace-wide discovery
   and Genie Ontology, not the selected curated agent's instruction boundary.
   Revalidate answer quality and permitted data for your use case.
2. Configure Genie One and obtain the workspace ID.
3. Grant the service, parent catalog/schema and underlying resource access
   described in [security](security.md). Review inherited grants.
4. Provision a **new** custom OAuth project connection with the exact Gateway
   target and `ai-gateway offline_access`. See [custom OAuth](custom-oauth.md).
5. Change local configuration:

   ```dotenv
   DATABRICKS_INTEGRATION_MODE=genie-one
   DATABRICKS_WORKSPACE_ID=<workspace-id>
   FOUNDRY_CONNECTION_MODE=existing-oauth
   FOUNDRY_CONNECTION_NAME=databricks-genie-one
   FOUNDRY_TOOLBOX_NAME=databricks-genie-one-toolbox
   ```

6. Remove/empty `DATABRICKS_GENIE_SPACE_ID` in both the file and shell.
7. Run offline validation, setup, and [live acceptance](validation.md).
   A new connection name requires its own per-user consent.
8. Switch selected agents to the new Toolbox only after validation. Keep the
   original pair available for consumers that still need curated behavior.

There is no need to delete the old route. Do not repoint a shared connection
as an automatic migration step.

## Users of the unsuffixed Genie One beta endpoint

The old Genie One beta endpoint is:

```text
https://<workspace-hostname>/api/2.0/mcp/genie
```

It is deprecated and reaches EOL **November 30, 2026**. Replace it with:

```text
https://<workspace-hostname>/ai-gateway/mcp-services/system.ai.genie_one_mcp?o=<workspace-id>
```

Request `ai-gateway` instead of `genie`, and ensure callers have service
access. The official notice says beta/GA Genie One tool names and arguments
are unchanged. It does **not** assert equivalence with curated Genie Agents.
[Authoritative migration notice](https://learn.microsoft.com/azure/databricks/agents/mcp-tools/genie-mcp#access-through-unity-gateway)

The original repository generated the space-specific URL, not this beta URL.

## Operational changes and deliberate stricter checks

- Existing shell entry points, override behavior, CLI commands and the five
  original configuration fields remain. New JSON output fields are additive.
- Both shell scripts now delegate to one Python setup routine.
- Failed inspections, malformed JSON and incomplete lists stop setup rather
  than causing attempted creation. Existing connection names/targets must
  match explicitly.
- Setup verifies OAuth2 authentication. Previously tolerated unknown or
  non-OAuth connection shapes now fail; reconcile them rather than weakening
  validation. Exposed custom scopes must include the API and refresh scopes.
- Inactive identifiers, empty/nested project paths and unsafe URL forms now
  fail with actionable errors.
- Raw connection responses are no longer persisted by setup. Existing local
  generated files are not deleted automatically; review and remove old
  diagnostics privately when appropriate.
- `existing-oauth` cannot use replacement flags. Managed replacement remains
  explicit and affects all consumers of that connection.
- The hygiene test checks Git tracking instead of local file existence.

These restrictions prevent wrong-target use and false provisioning success;
they do not certify any existing OAuth grant or live integration.
