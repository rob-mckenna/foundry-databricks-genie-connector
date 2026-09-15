# Security

## Supported configuration

The automated setup supports only the Foundry-managed OAuth connector for
Azure Databricks Genie. It does not accept bearer tokens, personal access
tokens, client secrets, or API keys.

## Secret handling

- Never add credentials to `.env`, command arguments, source files, issues, or
  logs.
- Do not invoke `azd ai connection show --show-credentials`.
- Store bring-your-own OAuth secrets in an organization-approved secret store
  and enter them directly in the Foundry or Databricks administrative UI.
- Rotate a credential immediately if it appears in Git history, chat, shell
  history, build logs, or a shared file.
- Review generated diagnostic logs before sharing them.

## Access control

- Grant the least Databricks permissions required by the Genie Agent.
- Prefer user identity passthrough so Unity Catalog evaluates the caller.
- Restrict Foundry project connection management to authorized operators.
- Review OAuth application scopes, redirect URLs, and token lifetimes.
- Treat prompts sent through the tool as data disclosed to Azure Databricks.

## Reporting a vulnerability

Report vulnerabilities privately to the repository owner. Do not include
credentials, customer data, or production endpoints in the report.

