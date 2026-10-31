# Virtual Data Scientist: current ML capabilities and proposed library set

Inspected October 31, 2026. Evidence: checked-in source and dependency manifests in the canonical repository and the older BI workbench, plus current library and AWS documentation. No new packages were installed, no model training was run, and the live cloud environment's installed versions were not queried.

## What the application uses today

The canonical repository is `/Users/scottleduc/Projects/virtual-data-scientist`. Its analytical worker uses Python's standard library and SQLite. Its dependency manifests declare AWS runtime/tracing/SDK packages and a PostgreSQL adapter:

- Root `requirements.txt`: `boto3>=1.34`, `psycopg[binary]>=3.2`.
- Root and agent `pyproject.toml`: `aws-opentelemetry-distro`, `bedrock-agentcore>=1.9.1`, `botocore[crt]>=1.35.0`.

No scikit-learn, XGBoost, statsmodels, NumPy, pandas, PyArrow, DuckDB, or openpyxl dependency or integration was found in the inspected application source and manifests. Local or managed environments could contain other installed packages; that does not make them an integrated application capability.

| Existing capability | Actual implementation | Limit |
| --- | --- | --- |
| Profiling and summaries | Counts, missingness, numeric/group summaries and date aggregation. | Uses CSV/SQLite; no Excel-to-Parquet path yet. |
| Driver diagnostics | Pearson correlations and grouped numeric summaries. | No fitted general-purpose regression model; correlation is not a causal result. |
| Classification diagnostics | Class counts and majority-class baseline accuracy. | No general classifier is trained by this worker. |
| Forecast diagnostic | Previous month's aggregate predicts the following observed month; computes historical mean absolute error. | No fitted forecasting model or general future-horizon forecast pipeline. |
| Segmentation diagnostics | Existing categories and candidate feature lists. | Does not fit K-means or another clustering model. |
| Outlier diagnostics | Absolute z-score of at least three. | Threshold diagnostic, not Isolation Forest; limited data scan. |
| Text diagnostics | Text lengths and token frequencies. | No embeddings or trained text classifier. |

Source: `analysis_engine/deep_worker.py:72`, `:115`, `:172`, `:204`, `:250`, and `:284`; method descriptions are in `analysis_engine/method_catalog.py`. The catalog's method names describe analytical intentions and should not be mistaken for implemented estimators. Some diagnostic queries cap rows or periods, so these outputs must not be presented as exhaustive analysis of an arbitrary upload.

The older `/Users/scottleduc/Projects/agentic-bi-report-platform` contains a genuine, small binary logistic-regression implementation in `model_registry/deal_risk.py:195`. It uses standard-library batch gradient descent, training-only standardization, and L2 regularization on synthetic deal-risk data. Its service compares the model with constant risk on a chronological holdout and supports a controlled registry workflow. This module has not yet been consolidated into the canonical repository. Preserve it as an evaluation and model-lifecycle example; use maintained library estimators for general uploaded datasets.

## Available from the proposed managed execution service

AWS currently lists these relevant Code Interpreter libraries as preinstalled: `scikit-learn`, `xgboost`, `statsmodels`, `scipy`, `numpy`, `pandas`, `polars`, `pyarrow`, `duckdb`, `openpyxl`, `matplotlib`, `seaborn`, `plotly`, and `torch`. [AWS library inventory](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/code-interpreter-preinstalled-libraries.html)

Code Interpreter is not yet connected to this app's analysis workflow. Its documented library inventory is distinct from this application's dependencies, and exact versions and required imports still need a live integration check. Installing an algorithm library also does not supply a suitable trained model for every upload. Classical models are fitted to the authorized dataset and saved with its version and evaluation evidence; pretrained weights and external model assets are a separate concern.

## Proposed first-release stack

| Layer | Libraries to adopt | Scope |
| --- | --- | --- |
| Typed ingestion and quick queries | `pyarrow`, `duckdb`, `openpyxl` | Parquet conversion, bounded queries, and XLSX parsing. |
| Numerical/data foundation | `numpy`, `pandas`, `scipy` | Feature preparation, arrays, statistics, and interoperability. |
| Core ML | `scikit-learn` | Estimators, preprocessing pipelines, validation splits, metrics, and basic explanations. |
| Statistical analysis and forecasting | `statsmodels` | Interpretable statistical fits and bounded time-series models. |
| Additional tree model | `xgboost` | An alternative candidate for regression/classification, enabled after the initial baselines work. |
| Output | `plotly`, `matplotlib` | Interactive chart specifications and static analytical figures. |

Keep the routing runtime small. Place the ML libraries in the execution environment and only the required parsing/query libraries in the ingestion/quick workers. Do not import or start the ML execution environment for every chart. Polars can remain an optional optimization until a measured bottleneck justifies a second DataFrame path. Record versions in every run and lock a compatible dependency set for the environments we control.

## Initial model menu

| Task | Candidates | Default policy |
| --- | --- | --- |
| Numeric prediction | Ridge or ElasticNet; histogram gradient boosting; optional XGBoost. | Dummy baseline, one linear candidate, one tree candidate. |
| Category prediction | Logistic regression; histogram gradient boosting; optional XGBoost. | Dummy baseline, linear candidate, tree candidate; select metrics for class imbalance and error costs. |
| Forecasting | Naive/seasonal-naive baseline, exponential smoothing, bounded SARIMAX where justified. | Match seasonality and horizon to available history; use chronological backtesting. |
| Segmentation | K-means or MiniBatchKMeans. | Scale appropriate numeric features; check stability and useful interpretation. |
| Outliers | Robust threshold baseline and Isolation Forest. | Explain why rows were flagged; review false positives. |
| Labeled text columns | TF-IDF with logistic regression or LinearSVC. | Optional later extension within the existing scikit-learn dependency. |

The scikit-learn reference covers the relevant [supervised methods](https://scikit-learn.org/stable/supervised_learning.html), [unsupervised methods](https://scikit-learn.org/stable/unsupervised_learning.html), and [preprocessing pipelines](https://scikit-learn.org/stable/modules/compose.html). Use pipelines to keep transformations fitted within the training procedure. [Statsmodels time-series reference](https://www.statsmodels.org/stable/tsa.html) describes the forecasting family. [XGBoost's estimator interface](https://xgboost.readthedocs.io/en/stable/python/sklearn_estimator.html) supports sklearn-compatible training and early stopping; use a validation split for stopping and preserve the final test set.

Cap a normal supervised job at one baseline plus up to two trained candidates. Compare candidate models on validation data, then evaluate the selected pipeline once on the untouched test set. Bound tree depth, estimators, fitting iterations, threads, and memory. A package import is only the beginning: each exposed method needs eligibility rules, a supported preprocessing path, evidence checks, and evaluation fixtures.

## Later additions with a specific justification

- **StatsForecast:** evaluate for many related series or intermittent demand, with bounded AutoETS/AutoARIMA or other eligible methods. Compare end-to-end cold and warm timings with the initial forecasting path. [Project documentation](https://nixtlaverse.nixtla.io/statsforecast)
- **SHAP:** evaluate for detailed per-prediction explanations when users need them. Begin with model coefficients and bounded scikit-learn permutation importance; add SHAP with sampled explanation budgets and clear limits on causal interpretation. [SHAP](https://shap.readthedocs.io/en/latest/), [permutation importance](https://scikit-learn.org/stable/modules/permutation_importance.html)

Do not assume these optional packages are present in the managed session; test packaging and compatibility separately. Defer GPU/deep-learning workflows, broad automated model searches, and open-ended hyperparameter tuning until a representative use case demonstrates a benefit within the time and cost budget.

## Next implementation check

Extend the existing execution spike with an import/version manifest, CSV/XLSX-to-Parquet round-trip, one classifier and one regressor with independent metrics, an outlier fixture, a chronological forecasting fixture, and chart retrieval. Verify that an ordinary aggregation makes no model-fitting call. A local contract test and a documented managed-service inventory do not by themselves confirm the deployed path; that requires the separately approved cloud execution trial.
