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
