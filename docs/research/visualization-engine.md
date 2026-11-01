# Visualization engine decision — November 1, 2026

Use **Plotly.js Cartesian 4.2.0** for analytical charts and **React Flow 12.12.0** for the agent monitor. This supersedes the previous ECharts adapter. Scientific diagnostics and readable Python exports now share Plotly figure conventions. The Python export pins Plotly 5.22.0, matching the execution sandbox; browser/Python package versions are different distributions.

| Option | Fit and decision |
|---|---|
| [Plotly.js](https://plotly.com/javascript/statistical-charts/) | Selected: statistical/scientific chart coverage, tooltips, zoom, legends, PNG/SVG export and [Python interoperability](https://plotly.com/python/). MIT licensed. The lazy-loaded Cartesian bundle covers the reviewed 2D analytical contract; this release does not enable arbitrary 3D graphics. |
| [Vega-Lite](https://vega.github.io/vega-lite/) and [Altair](https://altair-viz.github.io/) | Strong alternative for a composable grammar, faceting and linked selections. Requires a different figure/export contract. |
| [Apache ECharts](https://echarts.apache.org/en/feature.html) | Capable dashboard engine. Expanding its former adapter was viable, but scientific exports would continue to use a different Python renderer. Its unused local vendor bundles have been removed. |
| [D3](https://d3js.org/what-is-d3) | Useful for bespoke visual explanations; more custom interaction and export code than the analytical product currently needs. |
| [deck.gl](https://deck.gl/docs) | Future large geospatial data route; not necessary for current bounded tabular tasks. |

## Checked rendering boundary

The adapter accepts reviewed scatter, line, bar, heatmap, box and histogram traces. It bounds trace values to 1,200 points, heatmaps to 50 by 50 cells, rejects nonfinite numbers and escapes labels. Layout properties are copied through a small allowlist. Model-supplied functions, scripts, remote resources and arbitrary layout objects are never executed.

The product provides four persistent palettes, exact-value tables, tooltips, zoom/legend controls, PNG/SVG, figure JSON, figure JavaScript, figure Python and self-contained interactive HTML. Full task-specific ML reproduction is a separate analysis bundle/notebook. ROC/PR displays sample at most 1,000 points including endpoints; complete probabilities and curves remain in evidence/CSV. Projection previews are deterministic and bounded to 600 rows.

Bundles are pinned, self-hosted and license-preserving. `static/vendor/manifest.json` records distribution hashes and npm package integrity. Advisory scans do not exhaustively inspect code embedded inside a prebuilt vendor bundle. CSP remains self-only for scripts; no external chart CDN is required.

## Agent monitor

[React Flow](https://reactflow.dev/) retains parent-to-child arrows from the orchestrator to the actual participating agents, tools and checks. The default view is a single 42px status strip within the chat: labeled points use actual event states and expose full names/durations on hover/focus. Map mounts the detailed React Flow viewer. Status comes from persisted workflow events. Selection, keyboard details, reduced motion and viewport preservation are supported. It is an activity viewer, not a user-authored execution graph.

The build uses pinned dependencies and retains open-source license notices. See `frontend/workflow/`, `docs/plans/ml-showcase-and-exports.md` and the release acceptance evidence.
