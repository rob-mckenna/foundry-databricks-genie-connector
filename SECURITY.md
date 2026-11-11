# Security

## Supported configuration

The setup supports Foundry-managed OAuth for curated Genie Agents, and
reuse of an existing OAuth2 connection for either curated Genie Agents or
Genie One. It does not accept bearer tokens, personal access tokens, client
secrets or API keys. Genie One managed-connector compatibility is unverified
and automatic creation is blocked.

## Secret handling

- Never add credentials to environment files, command arguments, source,
  issues, chat or logs.
- Do not invoke `azd ai connection show --show-credentials` in this workflow.
- Store custom OAuth secrets in an approved credential store and enter them
  directly in the Foundry/Databricks administrative UI.
- Keep local environment files and generated output out of Git.
- Rotate credentials exposed in Git history, chat, shell history or logs.
- Setup withholds raw CLI diagnostics; inspect failures privately and review
  logs before sharing them.

## Access control

Foundry roles and Databricks permissions are separate. Use per-user OAuth
and verify identity isolation across agents and users. Genie One adds
Gateway service grants/policies; the curated MCP endpoint bypasses those
controls. Never substitute a shared identity to work around authorization.

Read the [full security and authorization model](docs/security.md) and
complete [live validation](docs/validation.md) before production use.
Pattern-based repository checks do not constitute a complete security audit.

## Reporting a vulnerability

Report vulnerabilities privately to the repository owner. Do not include
credentials, customer data, production endpoints or unredacted diagnostics.
