# Microsoft Foundry to Azure Databricks Genie

Customer-agnostic reference implementation for connecting a Microsoft Foundry
project to an Azure Databricks Genie Agent through the Databricks-managed MCP
server.

The default setup uses the Microsoft Foundry-managed OAuth connector and a
reusable Foundry Toolbox. It does not create, store, or pass bearer tokens,
client secrets, customer data, or tenant-specific identifiers.

> [!IMPORTANT]
> Azure Databricks managed MCP servers and some Foundry Toolbox capabilities
> are in public preview. Review current preview terms before production use.

## Architecture

```text
Foundry agent
    |
    v
Foundry Toolbox
    |
    v
Foundry project connection (managed OAuth)
    |
    v
https://<workspace>/api/2.0/mcp/genie/<space-id>
    |
    v
Azure Databricks Genie Agent and Unity Catalog permissions
```

## Prerequisites

- An existing Microsoft Foundry project and permission to manage project
  connections. The setup operator normally needs **Foundry Project Manager**;
  agent users need **Foundry User**.
- An Azure Databricks workspace with **Managed MCP Servers** enabled.
- An existing Genie Agent and its space ID.
- Permission to use that Genie Agent and its governed data.
- Python 3.10 or later.
- Azure Developer CLI (`azd`) with current Microsoft Foundry extensions.

Install or update the required extensions:

```powershell
azd extension install microsoft.foundry
azd extension install azure.ai.connections
azd extension install azure.ai.toolboxes
azd extension upgrade --all
```

Authenticate before setup:

```powershell
azd auth login
```

## Quick start

1. Copy `.env.example` to `.env`.
2. Replace the three resource placeholders.
3. Run the setup script for your shell.

PowerShell:

```powershell
Copy-Item .env.example .env
.\scripts\setup.ps1
```

Bash:

```bash
cp .env.example .env
bash ./scripts/setup.sh
```

The setup is safe to rerun. Existing connections and toolboxes are preserved
unless PowerShell is invoked with `-ReplaceConnection` or Bash with
`--replace-connection`.

## Complete first-user consent

After setup:

1. Open the Foundry project.
2. Open **Build > Tools** and select the created Toolbox.
3. Choose **Use in an agent**, or attach the Toolbox to an existing agent.
4. Send a question that requires Genie.
5. Open the consent link returned by Foundry.
6. Sign in to Azure Databricks and approve access.
7. Retry the question.

The initial `CONSENT_REQUIRED` response is expected for an OAuth connection.

## Offline validation

Configuration validation does not authenticate or contact Azure:

```powershell
$env:PYTHONPATH = "$PWD\src"
python -m foundry_databricks_genie.cli validate
python -m unittest discover -s tests -v
```

## Repository scope

This repository:

- creates a managed-OAuth Foundry project connection;
- creates a reusable Toolbox that references the connection;
- validates resource identifiers before cloud changes;
- documents manual consent, verification, troubleshooting, and cleanup.

It intentionally does not provision a Foundry project, deploy a model, create
a Databricks workspace or Genie Agent, grant data permissions, or commit
credentials.

## Documentation

- [Architecture and design decisions](docs/architecture.md)
- [Manual setup and verification](docs/manual-setup.md)
- [Custom OAuth fallback](docs/custom-oauth.md)
- [Security guidance](docs/security.md)
- [Troubleshooting](docs/troubleshooting.md)

## Official references

- [Use Azure Databricks Genie in Microsoft Foundry](https://learn.microsoft.com/azure/databricks/integrations/microsoft-foundry)
- [Azure Databricks managed MCP servers](https://learn.microsoft.com/azure/databricks/agents/mcp-tools/managed-mcp)
- [Connect Foundry agents to MCP endpoints](https://learn.microsoft.com/azure/foundry/agents/how-to/tools/model-context-protocol)
- [Create and manage a Foundry Toolbox](https://learn.microsoft.com/azure/foundry/agents/how-to/tools/toolbox)
