# Compact agents, reproducible analyses and ML showcase

November 1, 2026. Mode: productionization. Status: implemented and live-tested in the AWS development environment. The original proposal and starting-point evidence below describe source at `a5f7f47`. Current implementation and test results supersede the proposal language.

## Verified starting point

- The agent viewer uses React Flow. Its large canvas and detail pane are inside
  the selected run; deep-route canvas heights reach 520px desktop / 620px mobile
  before the surrounding UI. See `frontend/workflow/` and `static/workspace.js`.
- The browser uses ECharts through an adapter that accepts line/scatter traces
  rendered as lines and bar traces. The library supports more chart types than
  the current adapter exposes.
- Individual figure Python/JavaScript exports reconstruct checked chart data.
  They do not retrain a model. The ZIP includes the full `vds_recipe.py` and
  `ingestion.py`, but `analysis.py` and its notebook are thin launchers, and the
  UI labels do not make the distinction clear. See `analysis_engine/exports.py`
  and `static/experience.js`.
- Hosted AgentCore execution enables monthly summaries and forecasts. Forecasts
  compare a naive baseline, damped Holt (`statsmodels`) and a NumPy linear trend,
  select on chronological validation, and evaluate on a separate test period.
- Locally tested supervised recipes use scikit-learn preprocessing pipelines,
  dummy baselines, Ridge/LogisticRegression and RandomForest estimators. Those
  recipes are not integrated into the hosted planner/executor/presentation/export
  contract. Clustering, PCA and anomaly detection require new verified recipes.

## Recommended experience

One compact agent monitor stays pinned below the workspace header, rather than
repeating a large graph inside results. Target roughly 96–128px desktop and a
small wrapped mobile layout, to be verified at 390px width. Keep the orchestrator
above its selected children, actual event-driven active states, short labels,
keyboard-accessible details and usable touch targets. Hover/focus or selection
shows role, current action and elapsed time. An Expand control opens the existing
large graph and timeline. Idle/completed states must not pretend an agent is
working. Show which run the monitor represents when inspecting history.

Keep React Flow for this map. Analytical chart-engine choice is separate.

## Chart-engine options

| Option | Best fit | Tradeoff and recommendation |
|---|---|---|
| Plotly.js + Plotly Python | Statistical/scientific ML figures, interaction and consistent browser/Python exports | Recommended. Existing saved figure manifests and Python exports already use Plotly-style figures. Pin and self-host an appropriate build, loading analytical charts on demand; the full engine is substantial. |
| Vega-Lite + Altair | Composable statistical views, faceting and linked selections with a declarative specification | Strong alternative when a constrained chart grammar and linked exploration are the primary goals. Requires a new chart/export contract; not the first choice for scientific 3D views. |
| Expand the current ECharts adapter | Rich analytical dashboards with the smallest migration | Viable: scatter, heatmap, boxplot and parallel charts are already library capabilities. Current limitations partly come from our adapter. Python reproduction would still use another native engine. |

Sources checked:
- [Plotly statistical charts](https://plotly.com/javascript/statistical-charts/),
  [scientific charts](https://plotly.com/javascript/scientific-charts/),
  [image exports](https://plotly.com/javascript/static-image-export/),
  [MIT license](https://github.com/plotly/plotly.js/blob/main/LICENSE).
- [Vega-Lite overview](https://vega.github.io/vega-lite/docs/),
  [interactive selections](https://vega.github.io/vega-lite/docs/parameter.html),
  [Altair export documentation](https://altair-viz.github.io/user_guide/saving_charts.html).
- [ECharts capabilities](https://echarts.apache.org/en/feature.html).

A renderer migration alone does not implement new analytical methods. Extend
validated chart contracts for each task; continue excluding executable model
formatters, remote chart resources and arbitrary generated JavaScript.

## Analysis and export contract

Name figure downloads explicitly: Figure Python / Figure JavaScript. Offer a
separate Full analysis notebook / Reproducible analysis bundle action.

The analytical export should expose readable, task-specific code and notebook
sections for loading the exact prepared data, quality checks, split creation,
preprocessing, baseline, candidate fitting, validation selection, final held-out
evaluation and diagnostic figures. Library imports and `.fit()`/`.predict()`
calls should be visible where appropriate. Use statsmodels for supported time
series models and scikit-learn for supervised/clustering recipes; adding an
unused import does not make an analysis more complete.

Preserve feature exclusions, split IDs/cutoffs, seeds, package versions, source
hashes, preprocessing decisions, exact metrics and limitations. Keep all required
support source readable and included. In a fresh environment, the export must
reproduce the saved metrics within documented tolerances without calling the app.
Source-data inclusion remains an explicit download choice.

Regression needs baseline comparison, actual-vs-predicted and residual plots.
Classification needs class balance, confusion matrices and per-class metrics;
ROC/PR plots require appropriate labels and probabilities. Clustering needs
scaling, cluster profiles and valid stability/separation diagnostics. PCA needs
explained variance/loadings; label it as a projection. Anomaly detection needs
scores, threshold rationale and investigation context. Forecasts keep time-aware
splits and explicit limits on intervals/seasonality. No method is advertised as
implemented until it runs and passes its numerical checks in AgentCore.

## Curated sample gallery

| Dataset | Demonstration | Suggested question |
|---|---|---|
| Iris | Small multiclass classification | Which measurements help distinguish flower species? |
| Wine | Classification; later PCA/clustering using features only | Can we distinguish wine cultivars from their measurements? |
| Breast cancer diagnostic | Binary classification and class-specific errors | How well can these measurements distinguish the two recorded classes? |
| Diabetes | Regression and residual analysis | How accurately can the recorded outcome be predicted? |
| Palmer Penguins | Mixed types, missingness, exploration and classification | Which measurements help distinguish penguin species? |
| Seeded blobs/moons | Clustering and method limitations | What groups appear, and where does the clustering method struggle? |
| Seeded seasonal sales with anomalies | Forecasting and later anomaly detection | What is the trend, and which periods are unusual? |

These teaching examples are now implemented as frozen attributed snapshots.
Scikit-learn provides the first four loaders and generated examples:
[toy datasets](https://scikit-learn.org/stable/datasets/toy_dataset.html),
[generators](https://scikit-learn.org/stable/datasets/sample_generators.html).
Penguins has an official [dataset site](https://allisonhorst.github.io/palmerpenguins/).
Capture the specific upstream data license and citation for every published
snapshot; do not infer a data license from a software package license.

Each gallery card should show provenance, license, version/checksum, dimensions,
what it teaches, readiness and suggested questions. Load and profile through the
same ingestion path as uploads, without asking users to select technical columns.
Known teaching targets can come from catalog metadata; arbitrary uploads continue
to use profiling and business-context inference. Ask a business clarification
when the intended outcome is ambiguous.

Loading/profiling does not automatically submit or consume a model analysis. Run
Demo is an explicit action subject to the same account and global quotas.
Curated snapshots should work without network access inside the execution sandbox.

Add OpenML import after the curated gallery: accept stable dataset IDs/versions,
check metadata/licenses and size, cache immutable approved snapshots in S3 and
retain provenance. Begin with reviewed sources and bounded tabular formats, then
add search. Avoid unrestricted server-side URL fetches. OpenML exposes
[dataset/version/license metadata](https://docs.openml.org/reference/datasets/).
Do not imply the whole OpenML catalog has one license or is prevalidated.

## Implementation and acceptance sequence

1. Compact persistent agent monitor and clear figure-vs-analysis export labels.
   Verify small screens, active highlighting, selected-run identity, keyboard,
   reduced motion, streaming updates and expanded details.
2. Task-specific readable analytical exports and richer diagnostics. Execute
   exported notebooks/scripts in a clean environment and compare saved metrics.
3. Integrate the existing supervised recipes into the AgentCore planner,
   code-policy boundary, sandbox executor, numerical review, presentation,
   lessons, quotas and exports. Test classification/regression independently;
   this is more than enabling a task flag.
4. Add the curated gallery, with only deployed methods offered as runnable demos.
   Test profiling, ownership, snapshot reproducibility and target/leakage handling.
5. Add checked clustering/PCA/anomaly recipes and their matched example datasets.
6. Add bounded OpenML imports and broader exploration.

The cumulative ledger was 20/20 before this iteration. Posted shared-service cost estimates were approximately $0.40, with billing lag and attribution limits. The configuration ceiling was deliberately raised to 36 within the existing $10 allowance, preserving the cumulative ledger. Live classification/regression and export reproduction passed; clustering exposed a reviewer numeric-allowlist mismatch around the supplied preview limit, which was corrected without altering the numerical recipe. All six methods and a real browser upload/classification/export path passed. Ledger is now 30/36, including three confirmed failures retained in the counter. See `docs/deployment/2026-11-01-ml-showcase-verification.json`. Never reset the cumulative ledger or imply that local tests
prove AgentCore integration. Keep model tests bounded and data-only gallery
checks free of model calls.

Forecast correction: a training-only twelve-setting damped-Holt grid with known source initialization replaced continuous optimizer fitting after the new seasonal dataset exposed cross-library divergence. The numerical tolerances were not loosened. Current source, parameter evidence and exports use the same recipe; historical exports preserve their archived implementation.
