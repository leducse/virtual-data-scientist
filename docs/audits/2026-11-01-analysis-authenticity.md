# Analysis inputs, model execution and latency audit

November 1, 2026. This is an implementation/evidence audit of the hosted development workbench. The accompanying [machine-readable evidence](../deployment/2026-11-01-analysis-authenticity.json) contains only public Wine data metrics and fingerprints; no credentials or private source rows.

## What the current results establish

The inspected Wine classification and clustering runs used the real 178-row, thirteen-measurement UCI Wine dataset. The stored raw bytes and prepared Parquet were rehashed and matched the dataset and published-result fingerprints. Managed Interpreter stdout contained the candidate scores published by the app, and both sessions were confirmed terminated. A new browser upload of the Wine CSV also completed one real classification in AgentCore, with its own Interpreter session.

The frozen snapshot was independently compared to [UCI's original Wine download](https://archive.ics.uci.edu/dataset/109/wine). All 2,314 feature values matched within an absolute tolerance of 1e-12, and all 178 class labels matched after the documented one-based to zero-based mapping. Column headers and class numbering change the CSV byte hash, but the observations agree with the original source.

The exact downloaded classification script was executed in Python 3.12.13 with the recorded scientific package versions. It reproduced test balanced accuracy 0.9777777777777779. As a separate local negative control, the real feature rows were retained and class labels were intentionally shuffled into a different Parquet file. Validation scores changed and test balanced accuracy dropped to 0.3333333333333333. The original source/prepared files remained unchanged. This control was never used for a customer result and did not consume another hosted analysis.

## Implemented execution and data boundary

- `analysis_engine/cloud_service.py` prepares the supplied upload bytes, writes immutable source/Parquet and records hashes. Sample loading is a distinct explicit catalog action. Workers retrieve the selected owner-authorized dataset, verify prepared bytes, then pass those bytes to execution. There is no sample-data substitution on failure.
- `analysis_engine/cloud_execution.py` writes that Parquet and the reviewed recipe into a fresh AgentCore Code Interpreter, executes once and stops the session. Unknown outcomes fail explicitly and are never blindly replayed.
- `analysis_engine/code_policy.py` seals the supported ML program to approved recipe calls. The analyst selects/invokes reviewed computation; it does not fabricate numerical results.
- `analysis_engine/tabular.py` calls the actual fitting/prediction libraries. The Wine classification compares DummyClassifier, LogisticRegression and RandomForestClassifier, with training-only preprocessing and 106/36/36 training/validation/test rows. Clustering evaluates KMeans at k=2 through k=6 and uses PCA for its chart projection.
- Source/partition/baseline/metric/selection checks precede a separate Nova Pro review. Supervised numerical checking does not independently retrain every candidate; offline export reproduction additionally reruns the recorded candidate fitting for this audited Wine case.

## Supported model families

| Question/task | Current numerical implementation |
|---|---|
| Summary | DuckDB aggregation; no fitted ML model |
| Regression | DummyRegressor, Ridge, RandomForestRegressor |
| Classification | DummyClassifier, LogisticRegression, RandomForestClassifier |
| Forecast | Last-value baseline, NumPy linear trend, statsmodels damped Holt with a twelve-setting training-only grid |
| Clustering | Standardization, KMeans candidate group counts, silhouette comparison; PCA display projection |
| PCA | Standardization and scikit-learn PCA, variance/loadings/projection checks |
| Anomalies | IsolationForest scores/flags; PCA display projection |

The request selects the appropriate recipe and its candidate set. A classification does not also need an unrelated forecast, and a summary does not need model training. This is a bounded set of reviewed recipes, not an unrestricted AutoML search.

## Why it is fast

The inspected classification took 11.369 seconds end to end; clustering took 13.859 seconds, including 0.888 seconds in the numerical step. The new upload/classification took 14.095 seconds. Wine has only 178 rows and thirteen predictors. Forests are bounded to sixty trees and depth six; KMeans compares five candidate group counts. The source is already typed/prepared once, while models and the separate planner/analyst/reviewer calls run for each new deep request.

Reopening an existing run displays its stored result. Reusing the same request key returns that original run as an idempotency protection. Sending a new request key creates a new job and Interpreter session. Recorded compute duration and run time remain visible; page render latency is not represented as a new model fit.

## Dataset provenance and interpretation limits

Wine, Iris, breast cancer, diabetes and Penguins are attributed public datasets. Blobs, moons and seasonal sales are intentionally synthetic teaching examples and are labeled as such. Uploaded files retain uploader-supplied content; an upload label is not a certification that the underlying observations came from the real world. The app does not silently replace upload rows with generated observations.

Predictive methods retain held-out tests; clustering/PCA/anomalies are exploratory fits. The current recipes retain the documented row/feature limits and methodological assumptions. Small benchmark latency does not establish large-data throughput or generalization quality. Other supported methods retain their earlier [live acceptance](../deployment/2026-11-01-ml-showcase-verification.json); this audit independently reproduced Wine classification and inspected Wine clustering.
