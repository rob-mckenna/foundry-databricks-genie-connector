# Validation procedure and evidence

## Evidence boundaries

An offline test can prove URL construction, configuration rejection, rendered
output or mocked command sequencing. It cannot prove that Foundry issued the
right token, that Databricks accepted it, or that a query ran as the right user.

The **curated Genie Agent** route has executed a constant-query connectivity
test end to end: agent -> Toolbox -> existing OAuth connection -> Genie ->
`SELECT 1 AS connectivity_check`, with SQL success and the exact result `1`
verified. See the [November 9 live test](evidence/modernization-report.md#live-solution-test-november-9-2026).
This does not validate business-table authorization, cross-user isolation,
fresh consent, refresh/revocation, or Genie One.

Provisioning alone is still not runtime evidence. Setup correctly prints
NOT TESTED unless a separate invocation was actually performed. Do not treat
an unexposed scope warning as successful scope validation.

## Offline checks

From the repository root:

```powershell
$env:PYTHONPATH = "$PWD\src"
python -m unittest discover -s tests -v
```

CI runs the suite on Windows/Linux with Python 3.10 and 3.12, plus Bash and
PowerShell syntax checks. A configured CI matrix is not evidence that a
particular workflow run passed.

Coverage includes:

- Exact endpoints for both modes, including the Genie One workspace query.
- Legacy defaults, environment precedence and additive configuration output.
- Required/inactive identifiers, malformed modes and unsafe URLs.
- Toolbox rendering consistency and UTF-8 BOM input.
- Existing-resource reuse, explicit managed replacement and post-create checks.
- Failed/malformed/incomplete lookups, OAuth type and exposed-scope checks.
- Missing scopes reported as unverified, not silently approved.
- No credentials in commands, and no raw CLI diagnostics echoed on failure.
- Local environment files ignored by Git without preventing local setup.
- Bootstrap planning without SDK/cloud access, SDK serialization, dedicated
  agent ownership, pinned Toolbox references and active-agent routing checks.
- Consent continuation, explicit tool approval, bounded retries, secret-safe
  output and rejection of LLM-only/incomplete smoke-test evidence.
- Initial Responses requests omit `previous_response_id` until a continuation
  exists. Multiple JSON tool-output blocks and `structuredResponse` envelopes
  are inspected; uppercase failed/pending curated-query statuses cannot pass
  as completed queries.
- Existing-agent testing accepts portal-created agents without bootstrap
  metadata or binding/model environment variables, validates the saved pinned
  Toolbox and OAuth source, preserves resources, and rejects wiring drift.

Tests use synthetic connection responses and mocked subprocesses. Deployed
extension output compatibility must still be checked in a live environment.
Install `.[bootstrap]` to run the optional SDK contract tests. The
[guided bootstrap](bootstrap.md) can automate provisioning and part of the
live procedure below, but does not replace the identity/permission checks.

## Live acceptance: execute separately for each mode

Record PASS, FAIL, NOT TESTED or REQUIRES LIVE ENVIRONMENT for each step.
Keep evidence in an approved private location, not in this repository.
Record mode, client/extension versions and resource aliases, never tokens,
consent URLs, full connection payloads or customer query results.

### 1. Prepare identities and resources

- Use a non-production project/workspace and synthetic governed data.
- Create two users with deliberately different permitted rows/tables.
- Assign Foundry roles independently of Databricks permissions.
- For Genie One, configure the ontology/data and Gateway grants/policies.
- For curated mode, configure the agent, preview setting and data access;
  distinguish embedded compute credentials from end-user data privileges.
- Ensure runtime-to-Databricks network reachability and approved TLS settings.

### 2. Check the actual OAuth connection

- Verify exact target, provider, requested/allowed scopes and registered
  callback. Use `ai-gateway offline_access` for Genie One or
  `genie offline_access` for a custom curated connection.
- Verify the actual provider token's identity/workspace/scope behavior using
  approved diagnostics without printing or saving tokens.
- For the managed curated connector, confirm the effective grant instead of
  assuming its internal settings. Managed Genie One remains unsupported by
  this automation until separately verified.

### 3. Provision and discover tools

- Run setup with distinct names. Confirm it does not replace unrelated
  connections or Toolbox versions.
- Query `tools/list` through the version-specific Toolbox endpoint using the
  intended runtime. Verify the actual downstream tools, not just Toolbox
  existence.
- For Genie One, check the ask/poll/result/cancel tools. MCP Apps clients may
  expose `view_ask` instead of `genie_ask`; test the chosen client.

### 4. Run the complete path

For an existing saved agent, `test-agent` invokes it without provisioning.
Follow [the existing-agent workflow](bootstrap.md#test-an-existing-agent-without-provisioning);
do not use `bootstrap --apply` merely to test an externally created agent.

```text
Foundry Agent
  -> Toolbox
  -> OAuth project connection / per-user consent
  -> Unity Gateway MCP (Genie One) OR workspace MCP (curated)
  -> Genie
  -> governed query and returned result
```

- Attach two agents to the same Toolbox.
- For the first user, invoke a question, complete consent and resume/retry.
- Observe a successful data query/result, not merely `tools/list` or consent.
- Genie One: follow `in_progress` through sequential polling to a terminal
  response; check citations, conversation continuation, cancellation and
  explicit failed/incomplete responses. Test large-result truncation and
  `genie_get_query_result` without dumping results into logs.
- Curated mode: verify the selected agent is used and no conversation-history
  behavior is assumed.

### 5. Verify isolation, reuse and negative paths

- Invoke the second agent as the same user; check documented consent reuse.
- Invoke both agents concurrently as the second user. Confirm the second
  user's identity and data permissions, not the first user's cached session.
- Check Databricks query/audit evidence and, for Genie One, Gateway evidence.
  Do not expect Gateway traces for the curated endpoint.
- Deny/revoke data access and confirm no unauthorized rows are returned.
  Treat an empty curated response carefully: verify authorization, not just
  the response text.
- For Genie One, revoke service `EXECUTE` while retaining data access, then
  restore it. Separately deny underlying data access.
- For curated mode, remove agent access separately from underlying data access.
- Test missing scope, declined consent, expired access token with refresh,
  revoked/expired refresh grant, and re-consent.
- For hosted agents, validate per-request Foundry user context; the agent's
  credential alone is insufficient.
- Confirm a denied Foundry identity cannot bypass the Toolbox boundary.

### 6. Promote only after evidence

Validate the consumer endpoint/default version and both authorized users
after promotion. Record which modes were actually tested. Keep rollback
routes until consumers have migrated; replacing a connection can affect all
referencing Toolbox versions.

## Historical evidence

The [implementation evidence report](evidence/modernization-report.md) records dated
local and live checks performed while this reference was developed. It is an
audit trail, not proof that another deployment or the current product versions
will behave identically. Steps not covered by the recorded constant-query test
remain **REQUIRES LIVE ENVIRONMENT** until actual evidence is recorded.
