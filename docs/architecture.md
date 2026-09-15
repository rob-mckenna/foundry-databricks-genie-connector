# Architecture

## Design goals

- Work with any Microsoft Foundry project, Databricks workspace, and Genie
  Agent.
- Keep authentication in a Foundry project connection instead of agent code.
- Reuse the connection through an immutable, versioned Foundry Toolbox.
- Preserve Unity Catalog authorization through user OAuth identity.
- Avoid customer data, credentials, and environment identifiers in Git.

## Components

### Databricks managed Genie MCP server

Each Genie Agent exposes a managed MCP endpoint:

```text
https://<workspace-host>/api/2.0/mcp/genie/<genie-space-id>
```

Databricks hosts the MCP server. The Genie Agent and Unity Catalog determine
which governed data the signed-in user can access.

### Foundry project connection

The setup creates a `remote-tool` connection with:

- authentication type: `oauth2`;
- managed connector: `foundrydatabricksmcp`;
- target: the selected Genie MCP endpoint.

The project connection centralizes OAuth state and avoids embedding
authorization headers in an agent definition.

### Foundry Toolbox

The Toolbox references the project connection by name. It provides a reusable,
versioned MCP endpoint that can be attached to multiple agents without
duplicating connection configuration.

## Trust boundaries

Prompts and tool arguments cross from Foundry into Azure Databricks. Responses
cross back into Foundry. Databricks permissions remain authoritative for data
access. Repository configuration contains resource locations but no secrets.

## Deliberate exclusions

The repository does not:

- provision Azure or Databricks resources;
- create or configure a Genie Agent;
- grant Unity Catalog permissions;
- automate interactive user consent;
- use short-lived bearer tokens as a deployment mechanism;
- modify an existing Toolbox version.

