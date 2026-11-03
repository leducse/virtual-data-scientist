# React Flow activity viewer

Mode: productionization of the existing hosted analytics workspace.

Goal: replace the compact D3 pipeline with a React Flow canvas inspired by the
reference site's custom nodes, curved connections, dotted canvas and viewport
controls. React is mounted only inside the existing activity panel. Analytical
charts continue through ECharts.

Acceptance:

- Planner, query or analyst/Interpreter, numerical checks, reviewer and publication
  come from the actual selected route and persisted stage events. An undecided
  route shows only the orchestrator. No synthetic completion or progress values.
- Custom cards distinguish agents/tools/checks, show working/completed/waiting/
  stopped states and recorded duration/attempt, and expose step details on click.
- Pan, zoom, fit view, a larger canvas and keyboard-operable inspection work on
  desktop and mobile. The canvas is a viewer; it cannot alter execution.
- Stage updates preserve the React root, viewport and manual step selection.
  Changing a saved result disposes the old root. Reduced-motion preferences stop
  animations; text/status/timeline remain available.
- Dependencies are pinned, self-hosted, audited and reproducibly built. Publishing
  continues to use matching immutable asset URLs. No new backend or model scope.
- Node tests cover route/status/ordering and terminal/repair behavior. Browser
  checks cover controls, selection, update preservation, mobile and actual hosted
  stage rendering. Clearly distinguish local fixture replay from live execution.

## Coordination hierarchy correction

The default map represents parent–child coordination. Every selected agent,
tool, check and output has an outward arrow from the orchestrator; there are no
sibling-to-sibling arrows or numbered execution steps. The existing timeline
remains the source for execution order. The coordinator stays active after its
planning phase, until the run reaches a terminal state. Planning status/duration
and whole-job duration are separate facts in the inspector.

The current backend has two supported paths: quick query/check/publication, and
forecast analyst (including code writing)/Interpreter/check/review/publication.
The LLM planner selects the path; the application controller invokes its roles.
A separate code-writer agent and analyst-only explanatory route are not implemented.

Future selective routing could support explaining saved evidence without code
execution, generating code without executing it, and reusing approved recipes
without regenerating code. These require explicit task contracts, owner/evidence
checks, role budgets and validation policies before being exposed. No backend
capabilities or execution shortcuts are added by the map correction.
