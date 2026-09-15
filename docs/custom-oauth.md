# Bring-your-own OAuth fallback

Use this fallback only when the Foundry-managed Databricks connector is not
available or organizational policy requires a dedicated OAuth application.

## Databricks prerequisites

An Azure Databricks account administrator must create a custom OAuth
application connection with:

- approved Foundry redirect URL or URLs;
- the minimum required API scopes;
- appropriate access and refresh token lifetimes;
- a confidential client only when policy requires one.

Databricks notes that OAuth application changes can take up to 30 minutes to
propagate.

## Secret-safe procedure

1. Create the OAuth application in the Databricks account console.
2. Copy the client secret directly into an approved credential store. It
   cannot be retrieved later.
3. In the Foundry portal, create the Azure Databricks Genie tool or remote MCP
   project connection.
4. Enter the authorization URL, token URL, refresh URL, client ID, and client
   secret directly in the Foundry UI.
5. Never paste the secret into this repository, `.env`, a command line, chat,
   issue, or build log.

The automated scripts do not accept custom OAuth secrets because command-line
arguments and shell transcripts can expose them.

## Validation

After propagation, attach the connection through a Toolbox, invoke it from an
agent, and complete user consent. Confirm that the user receives only the data
authorized by Databricks.

