"""Trusted, fixed analytical recipes. No generated code is executed by the server."""
from __future__ import annotations

import importlib.metadata
import hashlib
import math
import time
from pathlib import Path
from analysis_engine.ingestion import InputError

RECIPE_SOURCE = Path(__file__).read_text()
RECIPE_SHA256 = hashlib.sha256(RECIPE_SOURCE.encode()).hexdigest()


def versions():
    return {name: importlib.metadata.version(name) for name in ["pyarrow", "duckdb", "numpy", "pandas", "scipy", "scikit-learn", "statsmodels"]}


def quote(name):
    return '"' + name.replace('"', '""') + '"'


def monthly_series(path, plan):
    import duckdb
    # File path is server-owned. Identifiers are checked against the stored schema.
    sql = f"""SELECT strftime({quote(plan.time_column)}, '%Y-%m') AS month,
                     sum({quote(plan.metric)}) AS value, count(*) AS records
              FROM dataset GROUP BY 1 ORDER BY 1 LIMIT 1201"""
    con = duckdb.connect(config={"threads": 1, "memory_limit": "256MB", "enable_external_access": False})
    try:
        import pyarrow.parquet as pq
        table = pq.read_table(path, columns=[plan.time_column, plan.metric])
        if any(table[c].null_count for c in table.column_names):
            raise InputError("Selected dates/measures contain missing values; clean them before aggregation.", "readiness_failed")
        con.register("dataset", table)
        rows = con.execute(sql).fetchall()
    finally:
        con.close()
    if len(rows) > 1200:
        raise InputError("Monthly series exceeds 1,200 periods.", "query_limit")
    return [{"month": month, "value": float(value), "records": records} for month, value, records in rows], sql


def quick_result(path, plan):
    started = time.monotonic()
    rows, sql = monthly_series(path, plan)
    result = {"task": plan.task, "series": rows, "total": sum(r["value"] for r in rows), "sql": sql,
              "chart": {"type": "line", "x": "month", "y": "value", "units": plan.units},
              "summary": f"{len(rows)} calendar months of {plan.metric}, summed from source rows.",
              "execution": "trusted_duckdb", "recipe_sha256": RECIPE_SHA256,
              "versions": {name: importlib.metadata.version(name) for name in ["pyarrow", "duckdb"]}, "timing_ms": {"query": round((time.monotonic()-started)*1000, 2)},
              "warnings": [plan.definition, f"Units: {plan.units}."]}
    # Independent Arrow aggregation catches grain/SQL errors without another model call.
    import pyarrow.parquet as pq
    expected = math.fsum(pq.read_table(path, columns=[plan.metric])[plan.metric].to_pylist())
    if not math.isclose(result["total"], expected, rel_tol=1e-10, abs_tol=1e-8):
        raise InputError("Independent aggregation check failed.", "evidence_rejected")
    result["review"] = {"passed": True, "checks": ["independent_total", "complete_selected_columns"], "kind": "deterministic"}
    return result


def mae(actual, predicted):
    return math.fsum(abs(float(a)-float(p)) for a, p in zip(actual, predicted)) / len(actual)


def forecast_values(method, train, horizon):
    import numpy as np
    if method == "naive":
        return np.repeat(train[-1], horizon).tolist()
    if method == "linear_trend":
        fit = np.polyfit(np.arange(len(train)), train, 1)
        return np.polyval(fit, np.arange(len(train), len(train)+horizon)).tolist()
    if method == "holt":
        from statsmodels.tsa.holtwinters import Holt
        return Holt(np.asarray(train), damped_trend=True, initialization_method="estimated").fit(optimized=True).forecast(horizon).tolist()
    raise ValueError("Unsupported method")


def forecast_result(path, plan, checkpoint=lambda stage: None):
    started = time.monotonic()
    rows, sql = monthly_series(path, plan)
    import pandas as pd
    dates = pd.PeriodIndex([r["month"] for r in rows], freq="M")
    if len(rows) < 12 or list(dates) != list(pd.period_range(dates[0], dates[-1], freq="M")):
        raise InputError("Forecasting needs at least 12 consecutive months. Missing months are not silently filled.", "readiness_failed")
    values = [r["value"] for r in rows]
    holdout = min(plan.horizon, max(1, len(values)//5))
    train_end, val_end = len(values)-2*holdout, len(values)-holdout
    if train_end < 6:
        raise InputError("Not enough training history for this horizon.", "readiness_failed")
    train, validation, test = values[:train_end], values[train_end:val_end], values[val_end:]
    candidates = {}
    for method in ["naive", "holt", "linear_trend"]:
        checkpoint("fitting " + method)
        predictions = forecast_values(method, train, len(validation))
        candidates[method] = {"validation_mae": mae(validation, predictions), "validation_predictions": predictions}
    selected = min(candidates, key=lambda m: candidates[m]["validation_mae"])
    checkpoint("evaluating untouched test")
    test_predictions = forecast_values(selected, values[:val_end], len(test))
    baseline_predictions = forecast_values("naive", values[:val_end], len(test))
    test_mae, baseline_mae = mae(test, test_predictions), mae(test, baseline_predictions)
    checkpoint("forecasting future months")
    future = forecast_values(selected, values, plan.horizon)
    next_dates = pd.period_range(dates[-1]+1, periods=plan.horizon, freq="M")
    result = {"task": "forecast", "series": rows, "forecast": [{"month": str(d), "value": float(v)} for d, v in zip(next_dates, future)],
              "chart": {"type": "line", "x": "month", "y": "value", "units": plan.units}, "sql": sql,
              "selected_method": selected, "candidates": candidates, "split": {"train_end": train_end, "validation_end": val_end, "count": len(values)},
              "test": {"actual": test, "predictions": test_predictions, "mae": test_mae, "baseline_predictions": baseline_predictions, "baseline_mae": baseline_mae},
              "summary": f"{selected} selected on validation MAE. Final test MAE {test_mae:.3g} {plan.units}; naive baseline {baseline_mae:.3g}. Forecast {plan.horizon} future months.",
              "warnings": ["No causal interpretation or calibrated prediction interval. Seasonal patterns are not modeled in this bounded recipe.",
                           "Final month is treated as complete; remove partial months before forecasting.", plan.definition],
              "versions": versions(), "seed": 42, "execution": "trusted_local_recipe", "recipe_sha256": RECIPE_SHA256,
              "timing_ms": {"analysis": round((time.monotonic()-started)*1000, 2)}}
    checkpoint("checking numerical evidence")
    result["review"] = review_forecast(path, plan, result)
    return result


def review_forecast(path, plan, result):
    """Rebuild input and recompute metrics; never trust the analyst's metric claims."""
    import pyarrow.parquet as pq
    rows = pq.read_table(path, columns=[plan.time_column, plan.metric]).to_pylist()
    grouped = {}
    for row in rows:
        month = str(row[plan.time_column])[:7]
        grouped[month] = grouped.get(month, 0.0) + row[plan.metric]
    series = result["series"]
    if [r["month"] for r in series] != sorted(grouped) or any(not math.isclose(r["value"], grouped[r["month"]], rel_tol=1e-10, abs_tol=1e-8) for r in series):
        raise InputError("Source aggregation does not match forecast input.", "evidence_rejected")
    split, test = result["split"], result["test"]
    n = len(series)
    a, b = split["train_end"], split["validation_end"]
    if not (6 <= a < b < n == split["count"]) or test["actual"] != [r["value"] for r in series[b:]]:
        raise InputError("Chronological split evidence is inconsistent.", "evidence_rejected")
    validation = [r["value"] for r in series[a:b]]
    if set(result["candidates"]) != {"naive", "holt", "linear_trend"}:
        raise InputError("Unapproved forecasting method.", "evidence_rejected")
    for method, candidate in result["candidates"].items():
        preds = candidate["validation_predictions"]
        trusted = forecast_values(method, [r["value"] for r in series[:a]], b-a)
        if len(preds) != len(trusted) or any(not math.isclose(p, t, rel_tol=1e-8, abs_tol=1e-8) for p,t in zip(preds,trusted)):
            raise InputError("Validation predictions do not match the training cutoff.", "evidence_rejected")
        if len(preds) != len(validation) or not math.isclose(mae(validation, preds), candidate["validation_mae"], rel_tol=1e-9, abs_tol=1e-9):
            raise InputError("False validation metrics.", "evidence_rejected")
    chosen = min(result["candidates"], key=lambda k: result["candidates"][k]["validation_mae"])
    if result["selected_method"] != chosen:
        raise InputError("Model selection did not use validation evidence.", "evidence_rejected")
    for key, pred_key in [("mae", "predictions"), ("baseline_mae", "baseline_predictions")]:
        preds = test[pred_key]
        if len(preds) != n-b or not all(math.isfinite(float(x)) for x in preds) or not math.isclose(mae(test["actual"], preds), test[key], rel_tol=1e-9, abs_tol=1e-9):
            raise InputError("False test metrics.", "evidence_rejected")
    trusted_test = forecast_values(chosen, [r["value"] for r in series[:b]], n-b)
    trusted_future = forecast_values(chosen, [r["value"] for r in series], plan.horizon)
    if any(not math.isclose(p,t,rel_tol=1e-8,abs_tol=1e-8) for p,t in zip(test["predictions"],trusted_test)):
        raise InputError("Test predictions violate the training cutoff.", "evidence_rejected")
    import pandas as pd
    expected_dates = [str(p) for p in pd.period_range(pd.Period(series[-1]["month"],freq="M")+1,periods=plan.horizon,freq="M")]
    if [r["month"] for r in result["forecast"]] != expected_dates or any(not math.isclose(r["value"],t,rel_tol=1e-8,abs_tol=1e-8) for r,t in zip(result["forecast"],trusted_future)):
        raise InputError("Future forecasts do not match the trusted refit.", "evidence_rejected")
    expected_baseline = [series[b-1]["value"]] * (n-b)
    if test["baseline_predictions"] != expected_baseline or len(result["forecast"]) != plan.horizon or any(not math.isfinite(r["value"]) for r in result["forecast"]):
        raise InputError("Baseline or future predictions are invalid.", "evidence_rejected")
    return {"passed": True, "kind": "independent_deterministic", "checks": ["source_aggregation", "chronological_partitions", "validation_selection", "recomputed_mae", "naive_baseline", "trusted_refit_at_cutoffs", "finite_forecast"],
            "limitations": "Numerical review; no independent language-model reviewer has run."}


def supervised_result(path, plan, checkpoint=lambda stage: None):
    import pandas as pd
    import numpy as np
    from sklearn.compose import ColumnTransformer
    from sklearn.pipeline import make_pipeline
    from sklearn.impute import SimpleImputer
    from sklearn.preprocessing import OneHotEncoder, StandardScaler
    from sklearn.model_selection import train_test_split
    from sklearn.dummy import DummyRegressor, DummyClassifier
    from sklearn.linear_model import Ridge, LogisticRegression
    from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
    from sklearn.metrics import mean_absolute_error, balanced_accuracy_score, f1_score
    from threadpoolctl import threadpool_limits

    df = pd.read_parquet(path, columns=[plan.metric, *plan.features])
    if len(df) < 60 or len(df) > 20_000 or df[plan.metric].isna().any():
        raise InputError("Supervised recipes need 60–20,000 rows and a complete target.", "readiness_failed")
    classification = plan.task == "classification"
    y = df[plan.metric].astype(str) if classification else pd.to_numeric(df[plan.metric], errors="raise")
    if classification and (y.nunique() > 10 or y.value_counts().min() < 10):
        raise InputError("Use 2–10 classes with at least 10 rows per class.", "readiness_failed")
    if classification and y.nunique() < 2:
        raise InputError("Classification needs at least two classes.", "readiness_failed")
    x = df[plan.features]
    # Catch direct target copies even when the misleading feature name looks safe.
    if any(x[c].astype(str).equals(y.astype(str)) for c in x.columns):
        raise InputError("A predictor duplicates the target.", "leakage_rejected")
    numeric = x.select_dtypes(include="number").columns.tolist()
    categorical = [c for c in x if c not in numeric]
    if any(x[c].nunique() > 100 for c in categorical):
        raise InputError("Categorical predictors must have at most 100 values.", "readiness_failed")
    ids = np.arange(len(df))
    train, remaining = train_test_split(ids, test_size=.4, random_state=42, stratify=y if classification else None)
    val, test = train_test_split(remaining, test_size=.5, random_state=42, stratify=y.iloc[remaining] if classification else None)
    def pipeline(model):
        prep = ColumnTransformer([
            ("number", make_pipeline(SimpleImputer(strategy="median", keep_empty_features=True), StandardScaler()), numeric),
            ("category", make_pipeline(SimpleImputer(strategy="most_frequent", keep_empty_features=True), OneHotEncoder(handle_unknown="ignore", sparse_output=False)), categorical)])
        return make_pipeline(prep, model)
    models = {"dummy": DummyClassifier(strategy="most_frequent") if classification else DummyRegressor(),
              "linear": LogisticRegression(max_iter=300, class_weight="balanced", random_state=42) if classification else Ridge(),
              "tree": RandomForestClassifier(n_estimators=60, max_depth=6, n_jobs=1, class_weight="balanced", random_state=42) if classification else RandomForestRegressor(n_estimators=60, max_depth=6, n_jobs=1, random_state=42)}
    score = balanced_accuracy_score if classification else mean_absolute_error
    candidates = {}
    fitted = {}
    with threadpool_limits(limits=1):
        for name, estimator in models.items():
            checkpoint("fitting " + name)
            fitted[name] = pipeline(estimator).fit(x.iloc[train], y.iloc[train])
            candidates[name] = float(score(y.iloc[val], fitted[name].predict(x.iloc[val])))
        selected = (max if classification else min)(candidates, key=candidates.get)
        checkpoint("evaluating untouched test")
        predictions = fitted[selected].predict(x.iloc[test])
        baseline = fitted["dummy"].predict(x.iloc[test])
    actual = y.iloc[test].tolist()
    metric = "balanced_accuracy" if classification else "mae"
    measured = float(score(actual, predictions))
    result = {"task": plan.task, "selected_method": selected, "selection_metric": metric, "candidates": candidates,
              "split": {"strategy": "random_60_20_20_seed42", "train": train.tolist(), "validation": val.tolist(), "test": test.tolist()},
              "test": {"actual": actual, "predictions": predictions.tolist(), metric: measured, "baseline": float(score(actual, baseline))},
              "summary": f"{selected} selected on validation {metric}; final test {metric}: {measured:.3g}.",
              "warnings": ["Random row split assumes independent observations. Repeated entities and temporal data require a different contract.", "Leakage screening detects names and direct copies; it cannot establish point-in-time correctness without domain review."],
              "execution": "trusted_local_recipe", "recipe_sha256": RECIPE_SHA256, "versions": versions(), "seed": 42}
    if classification:
        result["test"]["macro_f1"] = float(f1_score(actual, predictions, average="macro"))
        result["class_balance"] = {str(k): int(v) for k,v in y.value_counts().items()}
    checkpoint("checking numerical evidence")
    result["review"] = review_supervised(path, plan, result)
    return result


def review_supervised(path, plan, result):
    import pyarrow.parquet as pq
    from sklearn.metrics import mean_absolute_error, balanced_accuracy_score
    target = pq.read_table(path, columns=[plan.metric])[plan.metric].to_pylist()
    parts = [result["split"][key] for key in ["train", "validation", "test"]]
    if sorted(sum(parts, [])) != list(range(len(target))):
        raise InputError("Training partitions overlap or omit records.", "evidence_rejected")
    actual = [str(target[i]) if plan.task == "classification" else target[i] for i in parts[-1]]
    evidence = result["test"]
    if actual != evidence["actual"] or len(evidence["predictions"]) != len(actual):
        raise InputError("Test labels do not match source rows.", "evidence_rejected")
    metric = "balanced_accuracy" if plan.task == "classification" else "mae"
    score = balanced_accuracy_score if plan.task == "classification" else mean_absolute_error
    if not math.isclose(float(score(actual, evidence["predictions"])), evidence[metric], abs_tol=1e-10):
        raise InputError("Reported metric does not match predictions.", "evidence_rejected")
    return {"passed": True, "kind": "independent_deterministic", "checks": ["disjoint_partitions", "source_labels", "recomputed_metric"], "limitations": "Point-in-time feature availability requires domain review."}
