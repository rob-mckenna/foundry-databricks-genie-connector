# Security model

## Authentication

The primary flow uses a Foundry-managed OAuth connector. Interactive user
consent establishes delegated Databricks access without a bearer token in
source code.

## Authorization

OAuth authentication does not grant data access by itself. Databricks and
Unity Catalog permissions determine what the user and Genie Agent can access.
Validate least privilege with a user who has only the intended grants.

## Configuration classification

The Foundry project endpoint, Databricks workspace host, and Genie space ID are
not passwords, but they are environment metadata. Keep `.env` out of Git and
share values only through approved channels.

## Logging

- Do not enable verbose CLI diagnostics in shared pipelines.
- Do not request connection credentials when inspecting a connection.
- Review logs before attaching them to issues.
- Treat Genie prompts and responses as potentially sensitive business data.

## Production review

Before production use, review preview status, network controls, data residency,
audit logging, OAuth lifetimes, consent policy, Unity Catalog grants, incident
response, and operational ownership.

