"""Trusted, fixed analytical recipes. No generated code is executed by the server."""
from __future__ import annotations

import importlib.metadata
import hashlib
import math
import time
import platform
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
    result['python_version']=platform.python_version()
    return result


def mae(actual, predicted):
    return math.fsum(abs(float(a)-float(p)) for a, p in zip(actual, predicted)) / len(actual)


def fit_holt(train):
    """Fit a bounded training-only grid without platform-dependent optimization."""
    import numpy as np
    from statsmodels.tsa.holtwinters import Holt
    values=np.asarray(train,dtype=float)
    best=None
    for level in (.2,.5,.8):
        for trend in (.05,.2):
            for damping in (.9,.98):
                fitted=Holt(values,damped_trend=True,initialization_method='known',
                    initial_level=float(values[0]),initial_trend=float(values[1]-values[0])).fit(
                    smoothing_level=level,smoothing_trend=trend,damping_trend=damping,optimized=False)
                if not math.isfinite(fitted.sse):raise InputError('Holt fitting produced a nonfinite objective.','readiness_failed')
                if best is None or fitted.sse < best.sse and not math.isclose(fitted.sse,best.sse,rel_tol=1e-12,abs_tol=1e-12):best=fitted
    return best


def forecast_values(method, train, horizon, return_fit=False):
    import numpy as np
    if method == "naive":
        predictions=np.repeat(train[-1], horizon).tolist();parameters={'last_value':float(train[-1])}
    elif method == "linear_trend":
        fit = np.polyfit(np.arange(len(train)), train, 1)
        predictions=np.polyval(fit, np.arange(len(train), len(train)+horizon)).tolist();parameters={'slope':float(fit[0]),'intercept':float(fit[1])}
    elif method == "holt":
        fitted=fit_holt(train);predictions=fitted.forecast(horizon).tolist()
        parameters={key:float(fitted.params[key]) for key in ('smoothing_level','smoothing_trend','damping_trend','initial_level','initial_trend')}
        parameters.update(training_sse=float(fitted.sse),grid_size=12,selection='training_sse',initialization='known_first_observations')
    else:raise ValueError("Unsupported method")
    return {'predictions':predictions,'parameters':parameters} if return_fit else predictions


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
        fit = forecast_values(method, train, len(validation),return_fit=True)
        candidates[method] = {"validation_mae": mae(validation, fit['predictions']), "validation_predictions": fit['predictions'], 'fit':fit['parameters']}
    selected = min(candidates, key=lambda m: candidates[m]["validation_mae"])
    checkpoint("evaluating untouched test")
    test_fit = forecast_values(selected, values[:val_end], len(test),return_fit=True)
    test_predictions=test_fit['predictions']
    baseline_predictions = forecast_values("naive", values[:val_end], len(test))
    test_mae, baseline_mae = mae(test, test_predictions), mae(test, baseline_predictions)
    checkpoint("forecasting future months")
    future_fit = forecast_values(selected, values, plan.horizon,return_fit=True)
    future=future_fit['predictions']
    next_dates = pd.period_range(dates[-1]+1, periods=plan.horizon, freq="M")
    result = {"task": "forecast", "series": rows, "forecast": [{"month": str(d), "value": float(v)} for d, v in zip(next_dates, future)],
              "chart": {"type": "line", "x": "month", "y": "value", "units": plan.units}, "sql": sql,
              "selected_method": selected, "candidates": candidates, "split": {"train_end": train_end, "validation_end": val_end, "count": len(values)},
              'fitting':{'test':test_fit['parameters'],'future':future_fit['parameters']},
              "test": {"actual": test, "predictions": test_predictions, "mae": test_mae, "baseline_predictions": baseline_predictions, "baseline_mae": baseline_mae},
              "summary": f"{selected} selected on validation MAE. Final test MAE {test_mae:.3g} {plan.units}; naive baseline {baseline_mae:.3g}. Forecast {plan.horizon} future months.",
              "warnings": ["No causal interpretation or calibrated prediction interval. Seasonal patterns are not modeled in this bounded recipe.",
                           "Final month is treated as complete; remove partial months before forecasting.", plan.definition],
              "versions": versions(), "seed": 42, "execution": "trusted_local_recipe", "recipe_sha256": RECIPE_SHA256,
              "timing_ms": {"analysis": round((time.monotonic()-started)*1000, 2)}}
    checkpoint("checking numerical evidence")
    result["review"] = review_forecast(path, plan, result)
    result['python_version']=platform.python_version()
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
        fitted = forecast_values(method, [r["value"] for r in series[:a]], b-a,return_fit=True)
        trusted=fitted['predictions']
        if not numeric_evidence_equal(candidate.get('fit'),fitted['parameters']):
            raise InputError('Fitted parameters differ from the training-only fit.','evidence_rejected')
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
    for key,values in [('test',[r['value'] for r in series[:b]]),('future',[r['value'] for r in series])]:
        if not numeric_evidence_equal(result.get('fitting',{}).get(key),forecast_values(chosen,values,1,return_fit=True)['parameters']):
            raise InputError('Refit parameters differ from their source cutoff.','evidence_rejected')
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
    if classification and y.str.len().max()>100:
        raise InputError('Class names must be at most 100 characters.', 'readiness_failed')
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
    validation_predictions = {}
    fitted = {}
    with threadpool_limits(limits=1):
        for name, estimator in models.items():
            checkpoint("fitting " + name)
            fitted[name] = pipeline(estimator).fit(x.iloc[train], y.iloc[train])
            validation_predictions[name] = fitted[name].predict(x.iloc[val]).tolist()
            candidates[name] = float(score(y.iloc[val], validation_predictions[name]))
        selected = (max if classification else min)(candidates, key=candidates.get)
        checkpoint("evaluating untouched test")
        predictions = fitted[selected].predict(x.iloc[test])
        baseline = fitted["dummy"].predict(x.iloc[test])
    actual = y.iloc[test].tolist()
    metric = "balanced_accuracy" if classification else "mae"
    measured = float(score(actual, predictions))
    result = {"task": plan.task, "selected_method": selected, "selection_metric": metric, "candidates": candidates, "validation_predictions": validation_predictions, "features": plan.features,
              "split": {"strategy": "random_60_20_20_seed42", "train": train.tolist(), "validation": val.tolist(), "test": test.tolist()},
              "test": {"actual": actual, "predictions": predictions.tolist(), "baseline_predictions": baseline.tolist(), metric: measured, "baseline": float(score(actual, baseline))},
              "summary": f"{selected} selected on validation {metric}; final test {metric}: {measured:.3g}.",
              "warnings": ["Random row split assumes independent observations. Repeated entities and temporal data require a different contract.", "Leakage screening detects names and direct copies; it cannot establish point-in-time correctness without domain review."],
              "execution": "trusted_local_recipe", "recipe_sha256": RECIPE_SHA256, "versions": versions(), "seed": 42}
    if classification:
        result["test"]["macro_f1"] = float(f1_score(actual, predictions, average="macro"))
        result["class_balance"] = {str(k): int(v) for k,v in y.value_counts().items()}
    result['python_version'] = platform.python_version()
    if classification:
        from sklearn.metrics import classification_report, confusion_matrix, roc_curve, precision_recall_curve, roc_auc_score
        labels = fitted[selected].classes_.tolist()
        result['classes'] = labels
        result['confusion_matrix'] = confusion_matrix(actual, predictions, labels=labels).tolist()
        result['classification_report'] = classification_report(actual, predictions, labels=labels, output_dict=True, zero_division=0)
        from sklearn.metrics import precision_recall_fscore_support
        precision, recall, f1, support = precision_recall_fscore_support(actual,predictions,labels=labels,zero_division=0)
        result['per_class']=[{'label':label,'precision':float(p),'recall':float(r),'f1':float(f),'support':int(n)} for label,p,r,f,n in zip(labels,precision,recall,f1,support)]
        if len(labels) == 2:
            probabilities = fitted[selected].predict_proba(x.iloc[test])[:, 1]
            binary = np.asarray(actual) == labels[1]
            fpr, tpr, _ = roc_curve(binary, probabilities)
            precision, recall, _ = precision_recall_curve(binary, probabilities)
            result['test']['probabilities'] = probabilities.tolist()
            result['test']['roc_auc'] = float(roc_auc_score(binary, probabilities))
            result['roc'] = {'fpr': fpr.tolist(), 'tpr': tpr.tolist(), 'positive_class': labels[1]}
            result['precision_recall'] = {'precision': precision.tolist(), 'recall': recall.tolist()}
    else:
        from sklearn.metrics import r2_score, mean_squared_error
        result['test']['r2'] = float(r2_score(actual, predictions))
        result['test']['rmse'] = float(mean_squared_error(actual, predictions) ** .5)
        result['test']['residuals'] = (np.asarray(actual) - predictions).tolist()
    if classification:
        # Store each class name once; large supported datasets must fit bounded event responses.
        encoding={label:i for i,label in enumerate(result['classes'])}
        result['class_encoding']='index_into_classes'
        for key in ('actual','predictions','baseline_predictions'):
            result['test'][key]=[encoding[str(value)] for value in result['test'][key]]
        result['validation_predictions']={name:[encoding[str(value)] for value in rows] for name,rows in result['validation_predictions'].items()}
    checkpoint("checking numerical evidence")
    result["review"] = review_supervised(path, plan, result)
    return result



def numeric_evidence_equal(a,b):
    """Cross-environment floating arithmetic may differ by a few ULPs, not by counts/keys."""
    if isinstance(a,dict) and isinstance(b,dict):return set(a)==set(b) and all(numeric_evidence_equal(a[k],b[k]) for k in a)
    if isinstance(a,list) and isinstance(b,list):return len(a)==len(b) and all(numeric_evidence_equal(x,y) for x,y in zip(a,b))
    if isinstance(a,bool) or isinstance(b,bool):return type(a) is type(b) and a==b
    if isinstance(a,(int,float)) and isinstance(b,(int,float)):
        return a==b if isinstance(a,int) and isinstance(b,int) else math.isfinite(a) and math.isfinite(b) and math.isclose(a,b,rel_tol=1e-7,abs_tol=1e-7)
    return a==b

def review_supervised(path, plan, result):
    import pyarrow.parquet as pq
    from sklearn.metrics import mean_absolute_error, balanced_accuracy_score
    target = pq.read_table(path, columns=[plan.metric])[plan.metric].to_pylist()
    parts = [result["split"][key] for key in ["train", "validation", "test"]]
    if sorted(sum(parts, [])) != list(range(len(target))):
        raise InputError("Training partitions overlap or omit records.", "evidence_rejected")
    encoded=plan.task=='classification' and result.get('class_encoding')=='index_into_classes'
    classes=sorted(set(str(v) for v in target)) if encoded else None
    if encoded and result.get('classes')!=classes:raise InputError('Class encoding does not match source labels.', 'evidence_rejected')
    def outcome(i):
        return classes.index(str(target[i])) if encoded else str(target[i]) if plan.task=='classification' else target[i]
    actual = [outcome(i) for i in parts[-1]]
    evidence = result["test"]
    if actual != evidence["actual"] or len(evidence["predictions"]) != len(actual):
        raise InputError("Test labels do not match source rows.", "evidence_rejected")
    metric = "balanced_accuracy" if plan.task == "classification" else "mae"
    score = balanced_accuracy_score if plan.task == "classification" else mean_absolute_error
    if not math.isclose(float(score(actual, evidence["predictions"])), evidence[metric], abs_tol=1e-10):
        raise InputError("Reported metric does not match predictions.", "evidence_rejected")
    import numpy as np
    from sklearn.dummy import DummyClassifier, DummyRegressor
    baseline_model = DummyClassifier(strategy='most_frequent') if plan.task == 'classification' else DummyRegressor()
    baseline_model.fit(np.zeros((len(parts[0]), 1)), [str(target[i]) if plan.task == 'classification' else target[i] for i in parts[0]])
    baseline = baseline_model.predict(np.zeros((len(actual), 1))).tolist()
    if encoded:baseline=[classes.index(str(v)) for v in baseline]
    if not numeric_evidence_equal(baseline,evidence['baseline_predictions']) or not math.isclose(float(score(actual, baseline)), evidence['baseline'], abs_tol=1e-10):
        raise InputError('The baseline does not match the training partition.', 'evidence_rejected')
    validation_actual = [outcome(i) for i in parts[1]]
    if set(result['candidates']) != {'dummy', 'linear', 'tree'}:
        raise InputError('Candidate comparison is incomplete.', 'evidence_rejected')
    for name, value in result['candidates'].items():
        predicted = result['validation_predictions'][name]
        if len(predicted) != len(validation_actual) or not math.isclose(float(score(validation_actual, predicted)), value, abs_tol=1e-10):
            raise InputError('Validation metrics do not match their predictions.', 'evidence_rejected')
    selected = (max if plan.task == 'classification' else min)(result['candidates'], key=result['candidates'].get)
    if result['selected_method'] != selected:
        raise InputError('Selection did not use validation results.', 'evidence_rejected')
    if plan.task == 'classification':
        from sklearn.metrics import confusion_matrix, classification_report, f1_score, roc_auc_score, roc_curve, precision_recall_curve
        if 'classes' in result:
            labels = result['classes']
            predicted=evidence['predictions']
            if encoded:
                if any(type(v) is not int or not 0<=v<len(labels) for v in predicted):raise InputError('Invalid encoded prediction.', 'evidence_rejected')
                diagnostic_actual=[labels[v] for v in actual];diagnostic_predictions=[labels[v] for v in predicted]
            else:diagnostic_actual=actual;diagnostic_predictions=predicted
            if labels != sorted(set(str(v) for v in target)) or confusion_matrix(diagnostic_actual, diagnostic_predictions, labels=labels).tolist() != result['confusion_matrix']:
                raise InputError('Class diagnostics do not match source labels.', 'evidence_rejected')
            expected = classification_report(diagnostic_actual, diagnostic_predictions, labels=labels, output_dict=True, zero_division=0)
            from sklearn.metrics import precision_recall_fscore_support
            precision, recall, f1, support = precision_recall_fscore_support(diagnostic_actual,diagnostic_predictions,labels=labels,zero_division=0)
            per_class=[{'label':label,'precision':float(p),'recall':float(r),'f1':float(f),'support':int(n)} for label,p,r,f,n in zip(labels,precision,recall,f1,support)]
            if not numeric_evidence_equal(per_class,result['per_class']):raise InputError('Per-class values are inconsistent.', 'evidence_rejected')
            if not numeric_evidence_equal(expected,result['classification_report']) or not math.isclose(float(f1_score(actual, evidence['predictions'], average='macro')), evidence['macro_f1'], abs_tol=1e-10):
                raise InputError('Per-class metrics are inconsistent.', 'evidence_rejected')
            if len(labels) == 2:
                probabilities = np.asarray(evidence['probabilities'])
                binary = np.asarray(diagnostic_actual) == labels[1]
                if len(probabilities) != len(actual) or not np.isfinite(probabilities).all() or (probabilities < 0).any() or (probabilities > 1).any():
                    raise InputError('Invalid class probabilities.', 'evidence_rejected')
                fpr, tpr, _ = roc_curve(binary, probabilities)
                precision, recall, _ = precision_recall_curve(binary, probabilities)
                if not math.isclose(float(roc_auc_score(binary, probabilities)), evidence['roc_auc'], abs_tol=1e-10) or not np.allclose(fpr, result['roc']['fpr']) or not np.allclose(tpr, result['roc']['tpr']) or not np.allclose(precision, result['precision_recall']['precision']) or not np.allclose(recall, result['precision_recall']['recall']):
                    raise InputError('Probability diagnostics are inconsistent.', 'evidence_rejected')
    elif 'residuals' in evidence:
        from sklearn.metrics import r2_score, mean_squared_error
        if not np.allclose(np.asarray(actual) - evidence['predictions'], evidence['residuals']) or not math.isclose(float(r2_score(actual, evidence['predictions'])), evidence['r2'], abs_tol=1e-10) or not math.isclose(float(mean_squared_error(actual, evidence['predictions']) ** .5), evidence['rmse'], abs_tol=1e-10):
            raise InputError('Regression diagnostics are inconsistent.', 'evidence_rejected')
    return {"passed": True, "kind": "independent_deterministic", "checks": ["disjoint_partitions", "source_labels", "recomputed_metric", "training_baseline", "validation_selection", "diagnostic_consistency"], "limitations": "Random rows assume independent observations. Point-in-time feature availability requires domain review."}


def exploratory_matrix(path, plan):
    """Numeric exploration only; labels/identifiers never become distances."""
    import numpy as np
    import pandas as pd
    from sklearn.impute import SimpleImputer
    from sklearn.preprocessing import StandardScaler
    frame = pd.read_parquet(path, columns=plan.features)
    if not 20 <= len(frame) <= 20000 or not 2 <= len(frame.columns) <= 30:
        raise InputError('Exploration needs 20–20,000 rows and 2–30 numeric measurements.', 'readiness_failed')
    if any(not pd.api.types.is_numeric_dtype(frame[c]) for c in frame):
        raise InputError('Distance-based exploration needs numeric measurements.', 'readiness_failed')
    if np.isinf(frame.to_numpy(dtype=float)).any():
        raise InputError('Measurements contain infinite values.', 'readiness_failed')
    usable = [c for c in frame if frame[c].notna().any() and frame[c].nunique() > 1]
    if len(usable) < 2:
        raise InputError('At least two nonconstant measurements are required.', 'readiness_failed')
    x = StandardScaler().fit_transform(SimpleImputer(strategy='median').fit_transform(frame[usable]))
    return x, usable


def unsupervised_result(path, plan, checkpoint=lambda stage: None):
    """Bounded exploratory fits. No predictive accuracy or causal claim is implied."""
    import numpy as np
    from sklearn.cluster import KMeans
    from sklearn.decomposition import PCA
    from sklearn.ensemble import IsolationForest
    from sklearn.metrics import silhouette_score
    from threadpoolctl import threadpool_limits
    started = time.monotonic()
    x, features = exploratory_matrix(path, plan)
    count = len(x)
    preview = np.sort(np.random.default_rng(42).choice(count, min(count, 600), replace=False))
    with threadpool_limits(limits=1):
        checkpoint('fitting scaled principal components')
        pca = PCA(n_components=min(len(features), 10), svd_solver='full').fit(x)
        projected = pca.transform(x)
        result = {'task': plan.task, 'features': features, 'rows': count,
                  'preprocessing': 'Median imputation and standard scaling; constant/all-missing measurements excluded.',
                  'projection': {'row_indices': preview.tolist(), 'x': projected[preview, 0].tolist(), 'y': projected[preview, 1].tolist(),
                                 'components': pca.components_.tolist(), 'mean': pca.mean_.tolist(),
                                 'explained_variance': pca.explained_variance_.tolist(), 'explained_variance_ratio': pca.explained_variance_ratio_.tolist()},
                  'split': {'strategy': 'exploratory_all_rows_no_predictive_holdout'},
                  'warnings': ['Exploratory fits describe this dataset; they do not establish predictive performance or causation.',
                               'The 2D view uses at most 600 deterministically sampled rows; downloads retain complete assignments/scores.']}
        if plan.task == 'clustering':
            checkpoint('comparing bounded K-means cluster counts')
            candidates, fitted = {}, {}
            unique = len(np.unique(x, axis=0))
            for k in range(2, min(6, unique - 1, count // 5) + 1):
                model = KMeans(n_clusters=k, random_state=42, n_init=10, algorithm='lloyd').fit(x)
                if len(set(model.labels_)) != k:continue
                candidates[str(k)] = float(silhouette_score(x, model.labels_, sample_size=min(count, 500), random_state=42))
                fitted[str(k)] = model
            if not candidates:raise InputError('There are not enough distinct observations to compare clusters.', 'readiness_failed')
            selected = max(candidates, key=candidates.get)
            labels = fitted[selected].labels_
            result.update(selected_method='kmeans', selected_k=int(selected), candidates=candidates, labels=labels.tolist(),
                          centers=fitted[selected].cluster_centers_.tolist(), silhouette=candidates[selected],
                          cluster_counts={str(k): int((labels == k).sum()) for k in range(int(selected))},
                          summary=f'{selected} K-means groups selected by sampled silhouette ({candidates[selected]:.3f}); this is exploratory segmentation.')
            result['warnings'].append('K-means favors roughly compact groups; a high silhouette does not prove real-world categories or stability.')
        elif plan.task == 'pca':
            captured = float(sum(pca.explained_variance_ratio_[:2]))
            result.update(selected_method='pca', variance_first_two=captured,
                          summary=f'The first two principal components describe {captured:.1%} of standardized measurement variance.')
            result['warnings'].append('PCA is a linear projection of standardized measurements; component signs are arbitrary.')
        elif plan.task == 'anomaly_detection':
            checkpoint('fitting Isolation Forest')
            model = IsolationForest(n_estimators=100, max_samples=min(256, count), contamination='auto', random_state=42, n_jobs=1).fit(x)
            scores = -model.score_samples(x)
            threshold = float(-model.offset_)
            flags = (scores > threshold).astype(int)
            counts, edges = np.histogram(scores, bins=20)
            result.update(selected_method='isolation_forest', scores=scores.tolist(), flags=flags.tolist(), threshold=threshold,
                          flagged=int(flags.sum()), score_histogram={'counts': counts.tolist(), 'edges': edges.tolist()},
                          top_rows=np.argsort(-scores, kind='stable')[:20].tolist(),
                          summary=f'Isolation Forest flags {int(flags.sum())} of {count} rows using its automatic score threshold ({threshold:.3f}).')
            result['warnings'].append('A flag is an investigation lead, not a confirmed error. No labeled anomaly ground truth or calibrated probability is available.')
        else:raise InputError('Unsupported exploratory task.', 'unsupported_task')
    result.update(execution='trusted_local_recipe', versions=versions(), python_version=platform.python_version(),
                  recipe_sha256=RECIPE_SHA256, timing_ms={'fit': round((time.monotonic()-started)*1000, 2)})
    return result


def review_unsupervised(path, plan, result):
    import numpy as np
    from sklearn.metrics import silhouette_score, adjusted_rand_score
    x, features = exploratory_matrix(path, plan)
    if result.get('task') != plan.task or result.get('features') != features or result.get('rows') != len(x):
        raise InputError('Exploratory evidence does not match the prepared source.', 'evidence_rejected')
    projection = result['projection']
    components, mean = np.asarray(projection['components']), np.asarray(projection['mean'])
    covariance = np.cov(x, rowvar=False)
    eigenvalues = np.linalg.eigvalsh(covariance)[::-1][:len(components)]
    if not np.allclose(components @ components.T, np.eye(len(components)), atol=1e-6) or not np.allclose(
            components @ covariance @ components.T, np.diag(eigenvalues), rtol=1e-5, atol=1e-6):
        raise InputError('Principal axes fail independent source covariance checks.', 'evidence_rejected')
    if not np.allclose(projection['explained_variance_ratio'], eigenvalues / np.trace(covariance), rtol=1e-5, atol=1e-7):
        raise InputError('Explained variance does not match the source.', 'evidence_rejected')
    ids = projection['row_indices']
    expected_ids = np.sort(np.random.default_rng(42).choice(len(x), min(len(x), 600), replace=False)).tolist()
    if ids != expected_ids or not np.allclose(mean, x.mean(axis=0), atol=1e-7):
        raise InputError('The projection sample or centering changed.', 'evidence_rejected')
    points = (x[ids] - mean) @ components.T
    if not np.allclose(points[:, 0], projection['x'], atol=1e-6) or not np.allclose(points[:, 1], projection['y'], atol=1e-6):
        raise InputError('Projection points do not match the source and axes.', 'evidence_rejected')
    checks = ['source_measurements', 'covariance_eigenspectrum', 'orthonormal_axes', 'source_projection']
    if plan.task == 'clustering':
        labels = np.asarray(result['labels'])
        k = result['selected_k']
        if len(labels) != len(x) or set(labels) != set(range(k)):
            raise InputError('Cluster assignments are incomplete.', 'evidence_rejected')
        measured = float(silhouette_score(x, labels, sample_size=min(len(x), 500), random_state=42))
        centers = np.asarray([x[labels == i].mean(axis=0) for i in range(k)])
        counts = {str(i): int((labels == i).sum()) for i in range(k)}
        if k != int(max(result['candidates'], key=result['candidates'].get)) or not math.isclose(measured, result['silhouette'], abs_tol=1e-6) or not np.allclose(centers, result['centers'], atol=1e-6) or counts != result['cluster_counts']:
            raise InputError('Cluster diagnostics are inconsistent.', 'evidence_rejected')
        # A second, trusted fit checks selection and assignments independent of sandbox output.
        trusted = unsupervised_result(path, plan)
        if trusted['selected_k'] != k or adjusted_rand_score(trusted['labels'], labels) < .99999 or any(
                not math.isclose(v, trusted['candidates'].get(key, float('nan')), abs_tol=1e-5) for key, v in result['candidates'].items()):
            raise InputError('Cluster selection does not match a trusted refit.', 'evidence_rejected')
        checks.extend(['recomputed_silhouette', 'cluster_centers_counts', 'trusted_cluster_refit'])
    elif plan.task == 'pca':
        if not math.isclose(sum(projection['explained_variance_ratio'][:2]), result['variance_first_two'], abs_tol=1e-7):
            raise InputError('PCA summary differs from the checked components.', 'evidence_rejected')
    else:
        trusted = unsupervised_result(path, plan)
        if not np.allclose(trusted['scores'], result['scores'], atol=1e-6) or trusted['flags'] != result['flags'] or not numeric_evidence_equal(trusted['score_histogram'],result['score_histogram']) or trusted['top_rows'] != result['top_rows'] or trusted['flagged'] != result['flagged'] or trusted['threshold'] != result['threshold']:
            raise InputError('Anomaly scores do not match a trusted refit.', 'evidence_rejected')
        checks.append('trusted_isolation_forest_refit')
    return {'passed': True, 'kind': 'independent_deterministic', 'checks': checks,
            'limitations': 'Exploratory fit on all rows; no predictive holdout, causal interpretation or external cluster/anomaly labels.'}
