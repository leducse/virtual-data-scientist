# Architecture Diagrams

Primary project architecture:

- `virtual-data-scientist-architecture.svg`: rendered diagram for GitHub and
  portfolio use.
- `virtual-data-scientist-architecture.mmd`: Mermaid source for the same
  architecture.

The diagram intentionally separates the consulting website from the product
backend. The website is a client surface; the Virtual Data Scientist repo owns
the MCP/API facade, analysis engine, AgentCore runtime, backend state, and
artifacts.
