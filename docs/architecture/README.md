# Architecture Diagrams

The currently deployed development flow and its trust boundaries are documented
in [project context](../../project_context.md) and the actual resource manifest
in [deployment evidence](../deployment/README.md).

The following diagrams preserve the broader earlier architecture/design:

- `virtual-data-scientist-architecture.svg`: rendered diagram for GitHub and
  portfolio use.
- `virtual-data-scientist-architecture.mmd`: Mermaid source for the same
  architecture.

The diagram intentionally separates the consulting website from the product
backend. The website is a client surface; the Virtual Data Scientist repo owns
the MCP/API facade, analysis engine, AgentCore runtime, backend state, and
artifacts.
