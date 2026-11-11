# Contributing

Contributions should keep the repository customer-agnostic and secret-free.

Before opening a pull request:

1. Do not include customer names, real resource URLs, tenant IDs, workspace
   IDs, Genie space IDs, credentials, or captured responses.
2. Preserve managed OAuth as the default for curated Genie Agents. Do not
   enable it for Genie One without authoritative scope/endpoint support and
   live evidence. Keep existing-OAuth reuse secret-free.
3. Run:

   ```text
   python -m pip install -e ".[bootstrap]"
   python -m unittest discover -s tests -v
   ```

4. Update documentation when CLI behavior or prerequisites change.
5. Clearly identify behavior that depends on a preview feature.
6. Preserve both documented modes and the distinction between the deprecated
   unsuffixed beta endpoint and the supported space-specific endpoint.
7. Use synthetic fixtures and mocked cloud responses in offline tests.
   Do not delete a developer's ignored environment file to make tests pass.
8. Update the source register and migration/validation guidance when changing
   endpoint, OAuth, identity, scope or permission behavior. Never label a
   mocked test as an end-to-end cloud test.
9. Keep bootstrap opt-in and plan-only by default. Never bypass user consent,
   persist tokens/consent URLs, or count an LLM-only answer as tool execution.
