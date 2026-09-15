# Contributing

Contributions should keep the repository customer-agnostic and secret-free.

Before opening a pull request:

1. Do not include customer names, real resource URLs, tenant IDs, workspace
   IDs, Genie space IDs, credentials, or captured responses.
2. Preserve managed OAuth as the default authentication flow.
3. Run:

   ```text
   python -m unittest discover -s tests -v
   ```

4. Update documentation when CLI behavior or prerequisites change.
5. Clearly identify behavior that depends on a preview feature.

