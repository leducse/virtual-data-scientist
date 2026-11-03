"""Dependency-light local deep-analysis worker.

This worker is deliberately conservative. It runs deterministic summaries using
SQLite and standard-library statistics, then returns an auditable report plus
reproduction code. Heavier modeling can replace this worker later without
changing the analysis run lifecycle.
"""

from __future__ import annotations

import datetime as dt
from contextlib import closing
import re
import sqlite3
from pathlib import Path
from typing import Any

from analysis_engine.method_catalog import (
    choose_primary_method,
    leakage_candidates,
    meaningful_numeric_columns,
    method_details,
    target_candidates,
)


def quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def utc_now() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="seconds")


def fetch_rows(db_path: Path, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    with closing(sqlite3.connect(db_path)) as con:
        con.row_factory = sqlite3.Row
        return [dict(row) for row in con.execute(sql, params).fetchall()]


def top_counts(db_path: Path, table_name: str, column_name: str) -> list[dict[str, Any]]:
    table = quote_ident(table_name)
    column = quote_ident(column_name)
    return fetch_rows(
        db_path,
        f"""
        SELECT CAST({column} AS TEXT) AS value, COUNT(*) AS row_count
        FROM {table}
        WHERE {column} IS NOT NULL AND TRIM(CAST({column} AS TEXT)) <> ''
        GROUP BY CAST({column} AS TEXT)
        ORDER BY row_count DESC, value
        LIMIT 8
        """,
    )


def monthly_counts(db_path: Path, table_name: str, date_column: str) -> list[dict[str, Any]]:
    table = quote_ident(table_name)
    column = quote_ident(date_column)
    return fetch_rows(
        db_path,
        f"""
        SELECT substr(CAST({column} AS TEXT), 1, 7) AS period, COUNT(*) AS row_count
        FROM {table}
        WHERE {column} IS NOT NULL AND LENGTH(CAST({column} AS TEXT)) >= 7
        GROUP BY 1
        ORDER BY 1
        LIMIT 24
        """,
    )


def numeric_outliers(db_path: Path, table_name: str, column_name: str) -> dict[str, Any]:
    table = quote_ident(table_name)
    column = quote_ident(column_name)
    rows = fetch_rows(
        db_path,
        f"""
        SELECT {column} AS value
        FROM {table}
        WHERE {column} IS NOT NULL
        LIMIT 5000
        """,
    )
    values = [float(row["value"]) for row in rows if row["value"] is not None]
    if len(values) < 3:
        return {"column": column_name, "status": "not_enough_values", "outlier_count": 0}
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / (len(values) - 1)
    stddev = variance**0.5
    if stddev == 0:
        return {"column": column_name, "status": "constant", "outlier_count": 0}
    outlier_count = sum(1 for value in values if abs((value - mean) / stddev) >= 3)
    return {
        "column": column_name,
        "mean": round(mean, 4),
        "stddev": round(stddev, 4),
        "outlier_count": outlier_count,
        "outlier_rate_pct": round((outlier_count / len(values)) * 100, 2),
    }


def pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) != len(ys) or len(xs) < 3:
        return None
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True))
    denom_x = sum((x - mean_x) ** 2 for x in xs) ** 0.5
    denom_y = sum((y - mean_y) ** 2 for y in ys) ** 0.5
    if denom_x == 0 or denom_y == 0:
        return None
    return round(numerator / (denom_x * denom_y), 4)


def numeric_correlations(
    db_path: Path,
    table_name: str,
    target_column: str,
    candidate_columns: list[str],
) -> list[dict[str, Any]]:
    table = quote_ident(table_name)
    target = quote_ident(target_column)
    results = []
    for candidate_column in candidate_columns:
        if candidate_column == target_column:
            continue
        candidate = quote_ident(candidate_column)
        rows = fetch_rows(
            db_path,
            f"""
            SELECT {target} AS y, {candidate} AS x
            FROM {table}
            WHERE {target} IS NOT NULL AND {candidate} IS NOT NULL
            LIMIT 5000
            """,
        )
        xs = [float(row["x"]) for row in rows if row["x"] is not None and row["y"] is not None]
        ys = [float(row["y"]) for row in rows if row["x"] is not None and row["y"] is not None]
        corr = pearson(xs, ys)
        if corr is not None:
            results.append({"feature": candidate_column, "correlation": corr, "sample_size": len(xs)})
    return sorted(results, key=lambda item: abs(float(item["correlation"])), reverse=True)


def group_numeric_summary(
    db_path: Path,
    table_name: str,
    group_column: str,
    measure_column: str,
) -> list[dict[str, Any]]:
    table = quote_ident(table_name)
    group = quote_ident(group_column)
    measure = quote_ident(measure_column)
    return fetch_rows(
        db_path,
        f"""
        SELECT
          CAST({group} AS TEXT) AS group_value,
          COUNT(*) AS row_count,
          ROUND(AVG(CAST({measure} AS REAL)), 4) AS avg_value,
          ROUND(MIN(CAST({measure} AS REAL)), 4) AS min_value,
          ROUND(MAX(CAST({measure} AS REAL)), 4) AS max_value
        FROM {table}
        WHERE {group} IS NOT NULL AND {measure} IS NOT NULL
        GROUP BY CAST({group} AS TEXT)
        ORDER BY row_count DESC, group_value
        LIMIT 8
        """,
    )


def class_balance(db_path: Path, table_name: str, target_column: str) -> dict[str, Any]:
    table = quote_ident(table_name)
    target = quote_ident(target_column)
    rows = fetch_rows(
        db_path,
        f"""
        SELECT CAST({target} AS TEXT) AS class_value, COUNT(*) AS row_count
        FROM {table}
        WHERE {target} IS NOT NULL AND TRIM(CAST({target} AS TEXT)) <> ''
        GROUP BY CAST({target} AS TEXT)
        ORDER BY row_count DESC, class_value
        LIMIT 12
        """,
    )
    total = sum(int(row["row_count"]) for row in rows)
    classes = [
        {
            "value": row["class_value"],
            "row_count": row["row_count"],
            "rate_pct": round((int(row["row_count"]) / total) * 100, 2) if total else 0.0,
        }
        for row in rows
    ]
    majority = classes[0] if classes else None
    return {
        "target_column": target_column,
        "class_count": len(classes),
        "classes": classes,
        "majority_baseline_accuracy_pct": majority["rate_pct"] if majority else None,
    }


def naive_forecast_baseline(
    db_path: Path,
    table_name: str,
    date_column: str,
    measure_column: str,
) -> dict[str, Any]:
    table = quote_ident(table_name)
    date = quote_ident(date_column)
    measure = quote_ident(measure_column)
    periods = fetch_rows(
        db_path,
        f"""
        SELECT
          substr(CAST({date} AS TEXT), 1, 7) AS period,
          COUNT(*) AS row_count,
          ROUND(SUM(CAST({measure} AS REAL)), 4) AS actual_sum,
          ROUND(AVG(CAST({measure} AS REAL)), 4) AS actual_avg
        FROM {table}
        WHERE {date} IS NOT NULL AND LENGTH(CAST({date} AS TEXT)) >= 7 AND {measure} IS NOT NULL
        GROUP BY 1
        ORDER BY 1
        LIMIT 36
        """,
    )
    scored = []
    errors = []
    previous = None
    for period in periods:
        actual = float(period["actual_sum"] or 0)
        prediction = previous
        if prediction is not None:
            error = abs(actual - prediction)
            errors.append(error)
            scored.append({**period, "naive_prediction": round(prediction, 4), "absolute_error": round(error, 4)})
        else:
            scored.append({**period, "naive_prediction": None, "absolute_error": None})
        previous = actual
    return {
        "date_column": date_column,
        "measure_column": measure_column,
        "period_count": len(periods),
        "naive_mae": round(sum(errors) / len(errors), 4) if errors else None,
        "periods": scored,
    }


def text_diagnostics(db_path: Path, table_name: str, text_column: str) -> dict[str, Any]:
    table = quote_ident(table_name)
    column = quote_ident(text_column)
    rows = fetch_rows(
        db_path,
        f"""
        SELECT CAST({column} AS TEXT) AS text_value
        FROM {table}
        WHERE {column} IS NOT NULL AND TRIM(CAST({column} AS TEXT)) <> ''
        LIMIT 1000
        """,
    )
    stop_words = {"the", "and", "for", "with", "that", "this", "from", "have", "are", "was", "you"}
    lengths = []
    terms: dict[str, int] = {}
    for row in rows:
        text = str(row["text_value"])
        lengths.append(len(text))
        for term in re.findall(r"[A-Za-z][A-Za-z0-9_'-]{2,}", text.lower()):
            if term in stop_words:
                continue
            terms[term] = terms.get(term, 0) + 1
    top_terms = [
        {"term": term, "count": count}
        for term, count in sorted(terms.items(), key=lambda item: (-item[1], item[0]))[:12]
    ]
    return {
        "text_column": text_column,
        "non_empty_rows": len(rows),
        "avg_length": round(sum(lengths) / len(lengths), 2) if lengths else 0,
        "top_terms": top_terms,
    }


def baseline_diagnostics(db_path: Path, profile: dict[str, Any], method_type: str) -> dict[str, Any]:
    table = (profile.get("tables") or [{}])[0]
    table_name = table.get("table_name")
    if not table_name:
        return {"status": "no_table"}

    meaningful_numeric = meaningful_numeric_columns(table)
    categorical = table.get("categorical_columns", [])
    date_columns = table.get("date_columns", [])
    text_columns = table.get("text_columns", [])
    targets = target_candidates(table)

    diagnostics: dict[str, Any] = {"method_type": method_type, "table_name": table_name}
    if method_type == "forecasting" and date_columns and meaningful_numeric:
        diagnostics["forecasting"] = naive_forecast_baseline(db_path, table_name, date_columns[0], meaningful_numeric[0])
    if method_type == "regression_or_drivers" and meaningful_numeric:
        target = meaningful_numeric[0]
        diagnostics["driver_target"] = target
        diagnostics["numeric_correlations"] = numeric_correlations(db_path, table_name, target, meaningful_numeric[1:6])
        if categorical:
            diagnostics["grouped_target_summary"] = group_numeric_summary(db_path, table_name, categorical[0], target)
    if method_type == "classification_or_group_comparison":
        target = targets[0] if targets else (categorical[0] if categorical else None)
        if target:
            diagnostics["classification"] = class_balance(db_path, table_name, target)
            if meaningful_numeric:
                diagnostics["group_measure_summary"] = group_numeric_summary(db_path, table_name, target, meaningful_numeric[0])
    if method_type == "clustering_or_segmentation":
        diagnostics["candidate_features"] = [*meaningful_numeric[:4], *categorical[:4]]
        if categorical and meaningful_numeric:
            diagnostics["segment_profiles"] = group_numeric_summary(db_path, table_name, categorical[0], meaningful_numeric[0])
    if method_type == "anomaly_detection" and meaningful_numeric:
        diagnostics["numeric_outliers"] = [
            numeric_outliers(db_path, table_name, column)
            for column in meaningful_numeric[:6]
        ]
    if method_type == "text_analysis" and text_columns:
        diagnostics["text"] = text_diagnostics(db_path, table_name, text_columns[0])

    if len(diagnostics) == 2:
        diagnostics["status"] = "no_method_specific_baseline"
    return diagnostics


def quality_gates(profile: dict[str, Any], method_type: str) -> list[dict[str, Any]]:
    table = (profile.get("tables") or [{}])[0]
    targets = target_candidates(table)
    leaks = leakage_candidates(table)
    date_columns = table.get("date_columns", [])
    meaningful_numeric = meaningful_numeric_columns(table)
    row_count = int(table.get("row_count") or 0)

    gates = [
        {
            "name": "sample_size",
            "status": "pass" if row_count >= 100 else "warn",
            "detail": f"{row_count} rows available.",
        },
        {
            "name": "target_detection",
            "status": "pass" if targets else "warn",
            "detail": f"Potential targets: {', '.join(targets[:5])}" if targets else "No clear target column detected.",
        },
        {
            "name": "leakage_scan",
            "status": "warn" if leaks else "pass",
            "detail": f"Potential leakage fields: {', '.join(leaks[:5])}" if leaks else "No obvious leakage columns by name.",
        },
        {
            "name": "meaningful_measures",
            "status": "pass" if meaningful_numeric else "warn",
            "detail": (
                f"Meaningful numeric measures: {', '.join(meaningful_numeric[:5])}"
                if meaningful_numeric
                else "Only ID-like or unclear numeric fields were detected."
            ),
        },
    ]
    if method_type == "forecasting":
        gates.append(
            {
                "name": "time_split",
                "status": "pass" if date_columns else "fail",
                "detail": (
                    f"Use a time-aware split on {date_columns[0]}."
                    if date_columns
                    else "Forecasting requires a time column."
                ),
            }
        )
    return gates


def summarize_table(db_path: Path, profile: dict[str, Any]) -> dict[str, Any]:
    table = (profile.get("tables") or [{}])[0]
    table_name = table.get("table_name")
    if not table_name:
        return {"status": "no_table"}

    categorical = table.get("categorical_columns", [])
    date_columns = table.get("date_columns", [])
    meaningful_numeric = meaningful_numeric_columns(table)

    summaries: dict[str, Any] = {
        "table_name": table_name,
        "row_count": table.get("row_count"),
        "column_count": table.get("column_count"),
        "categorical_counts": {},
        "monthly_counts": {},
        "numeric_outliers": [],
    }
    for column in categorical[:4]:
        summaries["categorical_counts"][column] = top_counts(db_path, table_name, column)
    for column in date_columns[:2]:
        summaries["monthly_counts"][column] = monthly_counts(db_path, table_name, column)
    for column in meaningful_numeric[:4]:
        summaries["numeric_outliers"].append(numeric_outliers(db_path, table_name, column))
    return summaries


def ml_usefulness(primary_method: dict[str, Any], gates: list[dict[str, Any]]) -> dict[str, Any]:
    method_type = primary_method["type"]
    fail_or_warn = [gate for gate in gates if gate["status"] in {"fail", "warn"}]
    if method_type in {"not_enough_data", "descriptive_analysis"}:
        return {
            "decision": "not_yet",
            "reason": "Use descriptive analysis first; do not force ML until a target, measure, or decision goal is clear.",
        }
    if any(gate["name"] == "meaningful_measures" and gate["status"] != "pass" for gate in gates):
        return {
            "decision": "not_yet",
            "reason": "The selected table lacks meaningful non-ID numeric measures for modeling.",
        }
    return {
        "decision": "conditional",
        "reason": (
            "Modeling may be useful after resolving warnings: "
            + "; ".join(f"{gate['name']}: {gate['detail']}" for gate in fail_or_warn[:4])
            if fail_or_warn
            else "The data shape supports a cautious baseline model after a clear target is selected."
        ),
    }


def build_reproduction_code(profile: dict[str, Any], primary_method: dict[str, Any]) -> str:
    table = (profile.get("tables") or [{}])[0]
    table_name = table.get("table_name", "")
    return f'''#!/usr/bin/env python3
"""Reproduce the local deep-analysis worker summary.

This script intentionally uses only the Python standard library.
"""

import sqlite3
from pathlib import Path

DB_PATH = Path("data/poc_warehouse.sqlite")
TABLE_NAME = {table_name!r}
PRIMARY_METHOD = {primary_method["type"]!r}


def quote_ident(name):
    return '"' + name.replace('"', '""') + '"'


def main():
    table = quote_ident(TABLE_NAME)
    with sqlite3.connect(DB_PATH) as con:
        con.row_factory = sqlite3.Row
        row_count = con.execute(f"SELECT COUNT(*) AS c FROM {{table}}").fetchone()["c"]
        columns = con.execute(f"PRAGMA table_info({{table}})").fetchall()
        print({{"primary_method": PRIMARY_METHOD, "table": TABLE_NAME, "row_count": row_count}})
        print("columns", [row["name"] for row in columns])


if __name__ == "__main__":
    main()
'''


def run_local_deep_analysis(
    *,
    context_bundle: dict[str, Any],
    profile: dict[str, Any],
    db_path: Path,
) -> dict[str, Any]:
    user_question = str(context_bundle.get("user_question") or profile.get("user_question") or "")
    primary = choose_primary_method(profile, user_question)
    details = method_details(primary["type"])
    gates = quality_gates(profile, primary["type"])
    table_summary = summarize_table(db_path, profile)
    diagnostics = baseline_diagnostics(db_path, profile, primary["type"])
    usefulness = ml_usefulness(primary, gates)
    code = build_reproduction_code(profile, primary)

    report = {
        "title": "Local Deep Analysis Result",
        "status": "succeeded",
        "summary": (
            f"Recommended path: {details['label']}. {primary['reason']} "
            f"ML usefulness decision: {usefulness['decision']}."
        ),
        "primary_method": {
            **primary,
            "label": details["label"],
            "when_to_use": details["when"],
            "baseline": details["baseline"],
            "validation": details["validation"],
            "pitfalls": details["pitfalls"],
        },
        "ml_usefulness": usefulness,
        "quality_gates": gates,
        "table_summary": table_summary,
        "baseline_diagnostics": diagnostics,
        "next_steps": [
            "Confirm the business decision this analysis should support.",
            "Choose a target or primary metric before fitting predictive models.",
            "Keep the generated code artifact attached to the session for reproducibility.",
            "Escalate to AgentCore only when the worker needs longer code execution or iterative modeling.",
        ],
        "context_bundle": context_bundle,
        "generated_at": utc_now(),
    }
    return {"report": report, "code": code}
