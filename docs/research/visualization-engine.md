# Visualization engine decision — October 31, 2026

Use Apache ECharts **6.1.0** for the analytical workspace and D3.js **7.9.0** for the agent activity diagram. Versions and licenses were checked against the npm package metadata, and the published package bundles are pinned and self-hosted with their license/NOTICE files. This is a fit decision for this product, rather than a universal ranking.

| Library | Strength for this application | Decision |
| --- | --- | --- |
| [Apache ECharts](https://echarts.apache.org/handbook/en/basics/release-note/v6-feature/) | Broad analytical chart types; time and category axes; tooltips, legends, zoom, linked views, SVG/canvas renderers, ARIA and decals. Apache 2.0. | Main browser renderer. SVG suits the bounded 1,200-point trusted figures and provides vector exports. |
| [D3.js](https://d3js.org/what-is-d3) | Low-level data joins, shapes, scales, layouts and interaction for unusual visual explanations. ISC. | Bespoke orchestrator/subagent diagram, driven by actual saved stage events. |
| [Plotly.js](https://plotly.com/javascript/) | Scientific/statistical and 3D chart coverage, strong Python interoperability. MIT. | Keep existing evidence manifests and Python chart exports compatible. Browser rendering moves to ECharts. |
| [Vega-Lite](https://vega.github.io/vega-lite/) | Concise declarative statistical grammar, composition and interactive selections. BSD 3-Clause. | Strong alternative for a future chart authoring grammar; adding a second main chart engine now would duplicate validation and exports. |
| [Highcharts](https://www.highcharts.com/docs/accessibility/accessibility-module) | Extensive charting and a dedicated accessibility module. Its [license agreement](https://shop.highcharts.com/license) distinguishes internal, SaaS and OEM uses. | A credible commercial alternative; the selected open-source stack avoids adding a commercial chart license to this development preview. |
| [Observable Plot](https://observablehq.github.io/plot/) | Concise layered marks, transforms and small multiples, built with D3. ISC. | Attractive for exploratory/statistical authoring; ECharts is the stronger fit for the chosen dashboard interaction and export contract. |
| [deck.gl](https://deck.gl/docs) | WebGPU/WebGL2 rendering, picking, filtering and map integration for large spatial datasets. | Consider for a future geospatial task; current bounded monthly series do not need this additional renderer. |

Three.js is a general 3D graphics engine. Current questions are monthly trends and checked forecasts, so added dimensionality would obscure these comparisons. Scientific 3D or geographic views should be introduced when a dataset and analytical task justify them.

## Implemented interaction and evidence boundary

- Rich-text crosshair tooltips, scrollable legends, axis zoom/restore and a range slider. Ctrl + wheel zoom avoids capturing normal page scrolling.
- Linked time-axis views within one run; categorical method comparisons are deliberately kept outside that group.
- Four persistent palettes, SVG rendering, ARIA/decal support, and exact-value tables for every figure. These features do not constitute a full accessibility audit.
- PNG, SVG, self-contained interactive HTML, ECharts JSON/JavaScript, and Python/Plotly exports. Python regenerates the same checked data with its native engine; visual styling is not pixel-identical.
- The adapter accepts validated line/bar data only. It does not execute model-generated chart code, formatters, HTML or remote resources. Additional library capabilities require reviewed chart types and tests before exposure.
- Forecast holdouts, validation errors and historical/forecast values remain distinct, preserving their units and split labels.

Relevant primary references: [SVG/canvas tradeoffs](https://echarts.apache.org/handbook/en/best-practices/canvas-vs-svg/), [ARIA/decal guidance](https://echarts.apache.org/handbook/en/best-practices/aria/), [D3 API](https://d3js.org/api).

The exact bundle hashes, package integrity values and observed dependency audit are recorded in `static/vendor/manifest.json`.

## Subsequent workflow decision — React Flow

After reviewing the requested [React Flow site](https://reactflow.dev/), its
[custom node API](https://reactflow.dev/learn/customization/custom-nodes) and
[accessibility guidance](https://reactflow.dev/learn/advanced-use/accessibility),
the workflow viewer now uses React Flow 12.12.0. This supersedes the D3 choice
for the agent map above; ECharts remains the analytical engine. Core React Flow
is MIT licensed. The implementation uses original custom node UI and the open
core library, with its attribution and bundled license notices retained.

It provides measured node/edge layout, pan/zoom, controls and accessible React
components. The app adds event-derived statuses and inspection, a compact mobile
route, reduced motion and root/viewport preservation. Dependencies are pinned in
`frontend/workflow/package-lock.json`; the audit reports zero vulnerabilities.
