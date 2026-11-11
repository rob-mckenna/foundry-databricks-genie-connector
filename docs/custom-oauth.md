# OAuth setup and existing connections

## Managed versus custom OAuth

For `genie-agent`, `managed-oauth` uses the documented
`foundrydatabricksmcp` connector without a client ID or secret in this repository.
Foundry supplies the managed application's OAuth settings.

For `genie-one`, or when policy requires your own OAuth application, create a
custom OAuth project connection and select `existing-oauth`. This changes who
owns the application registration, **not** who stores/injects user tokens:
Foundry still manages OAuth on behalf of each consenting user.

Managed connector support for the Genie One URL and `ai-gateway` scope is
unverified. Do not combine `--connector-name` with custom OAuth scope or
credential flags. This repository intentionally does not automate that
combination. [Microsoft's configuration contract](https://learn.microsoft.com/azure/foundry/agents/how-to/tools/model-context-protocol)

## Required configuration

| Setting | Genie One | Curated Genie Agent |
| --- | --- | --- |
| Target | Gateway URL including `?o=<workspace-id>` | Workspace URL including `/api/2.0/mcp/genie/<space-id>` |
| API scope | `ai-gateway` | `genie` |
| Refresh scope for this reference pattern | `offline_access` | `offline_access` |
| Foundry auth type | OAuth identity passthrough / OAuth2 | OAuth identity passthrough / OAuth2 |

Scopes permit API use; they do not grant access to a Gateway service, agent
or table. Keep app-allowed scopes and connection-requested scopes aligned.
Do not request `all-apis` merely to hide a scope error.

### API scopes versus identity scopes

The table above lists the service and refresh scopes; it is not proof that
those two scopes alone satisfy every provider identity flow.

Databricks documents that its **UI-created** custom applications automatically
allow `openid`, `email`, `profile` and `offline_access`. API-created applications
can instead use an explicitly restricted scope list. The original scripted
application explicitly allowed only `genie` and `offline_access`, so it did
not reproduce all of the UI defaults.

Allowed scopes on the Databricks application and requested scopes on the
Foundry connection are separate settings. Allowing a scope does not mean
Foundry requests it. Configure both appropriately for the chosen identity
flow, including OIDC identity scopes when applicable, and obtain fresh user
consent as needed. These scopes do not replace Unity Catalog permissions.
Matching configured scopes is not proof of successful consent or token
exchange. Verify the complete connection in the target environment.

## Secret-safe procedure

1. Have a Databricks account administrator register a custom OAuth application.
   Use the [official application setup](https://learn.microsoft.com/azure/databricks/integrations/enable-disable-oauth#enable-custom-app-ui);
   use its documented API option if fine-grained scopes are not exposed in the UI.
2. Create a remote MCP project connection in Foundry with your selected target
   and **OAuth identity passthrough / Custom OAuth**.
3. Configure the application's client ID, authorization URL, token URL,
   refresh URL and scopes in the Foundry administrative UI. For workspace
   OAuth, use that workspace's `/oidc/v1/authorize` and `/oidc/v1/token`
   endpoints; the token endpoint also handles refresh.
4. Register the **exact redirect URL returned by Foundry** in the Databricks
   OAuth application. Do not copy another project's callback or invent one.
   Follow the UI's creation order if it provides the callback during setup.
5. Use a confidential client where required. Store its secret directly in an
   approved credential store/Foundry configuration. Public clients have
   different requirements; do not assume a client-ID-only flow works with
   every Foundry UI/CLI version.
6. Set the selected API scope plus `offline_access`, and align any applicable
   OIDC identity scopes on the app and connection as described above. Foundry's custom OAuth
   UI/API uses space-separated scopes; `azd --scopes` uses repeated or
   comma-separated values. These scripts do not accept OAuth credential flags.
7. Allow for propagation: Databricks documents that OAuth application changes
   can take up to 30 minutes.
8. Configure `FOUNDRY_CONNECTION_MODE=existing-oauth` and the exact connection
   name, then run setup. Setup only inspects this connection and references it
   from the Toolbox; it cannot create, alter or replace it.

Databricks requires a preconfigured OAuth client; its MCP endpoints do not
support dynamic client registration. Use Streamable HTTP.
[Databricks client requirements](https://learn.microsoft.com/azure/databricks/ai-gateway/coding-agent-mcp-skills#other-mcp-clients)

## What setup can verify

Setup verifies the connection name, exact target and exposed OAuth2 auth type.
It checks the connection category when emitted. For existing OAuth
connections, it checks both required scopes **if `azd` exposes them**. If
scopes are omitted/redacted, setup emits a **NOT VERIFIED** warning; it does
not request credentials to recover them or claim authentication works.
Verify scopes in the administrative UI and perform live tests before use.

A scope field is configuration evidence, not proof of the issued token's
scope, expiry, audience, or identity. Managed app scopes and tokens are not
inspected by this repository.

## Consent, token lifecycle and audience

Foundry requests provider consent for each new user/connection/project
combination. Toolboxes can report MCP `CONSENT_REQUIRED` (`-32006`); agent
Responses APIs can return `oauth_consent_request` with a `consent_link`.
After authorization, retry/resume the request through the appropriate client.
Opening a link alone is not evidence of completed consent.

Foundry stores and refreshes provider credentials; the connector neither
obtains nor caches Databricks OAuth tokens. Optional bootstrap uses the Azure
SDK and the operator's `azd` login to obtain Foundry access tokens in memory;
these are never copied into agent definitions or sent to Databricks.
Refresh requires the refresh scope and a valid refresh grant.
Consent may need repeating after expiry, revocation, application changes or
use of a new connection name. Verify reuse across agents and isolation between
users rather than sharing a bearer token.

The downstream credential must authorize Databricks operations for the
intended workspace and user. A Foundry/ARM token is not a substitute.
Provider OAuth identity passthrough is not automatically Microsoft Entra
`AgentOnBehalfOfUser`. Exact issued-token audience/issuer behavior for the
managed connector was not verified; validate with approved provider
diagnostics without logging tokens.

Sources: [Foundry OAuth](https://learn.microsoft.com/azure/foundry/agents/how-to/mcp-authentication),
[Databricks U2M](https://learn.microsoft.com/azure/databricks/dev-tools/auth/oauth-u2m),
[Databricks MCP authentication](https://learn.microsoft.com/azure/databricks/agents/mcp-tools/authentication-networking).
