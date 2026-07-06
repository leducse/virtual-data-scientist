"""Method-selection catalog for the dependency-light local worker."""

from __future__ import annotations

from typing import Any


METHOD_CATALOG: dict[str, dict[str, Any]] = {
    "descriptive_analysis": {
        "label": "Descriptive analysis",
        "when": "The user needs to understand what is in the data before modeling.",
        "baseline": "Schema profile, missingness, distributions, group counts, and trend counts.",
        "validation": ["Verify row counts", "Check missingness", "Inspect high-cardinality fields"],
        "pitfalls": ["Overstating causality", "Treating IDs as measures"],
    },
    "regression_or_drivers": {
        "label": "Regression / driver analysis",
        "when": "There is a numeric outcome with plausible explanatory fields.",
        "baseline": "Correlations and simple grouped summaries before fitting a model.",
        "validation": ["Target availability", "Leakage check", "Train/test split", "Residual review"],
        "pitfalls": ["Using identifiers as predictors", "Calling correlation causal"],
    },
    "classification_or_group_comparison": {
        "label": "Classification / group comparison",
        "when": "There is a categorical outcome or useful segment label.",
        "baseline": "Class balance, segment rates, and majority-class baseline.",
        "validation": ["Class imbalance", "Leakage check", "Precision/recall or ROC-AUC"],
        "pitfalls": ["Accuracy on imbalanced labels", "Ambiguous target definitions"],
    },
    "forecasting": {
        "label": "Forecasting",
        "when": "There is a time column and a meaningful time-indexed metric.",
        "baseline": "Naive or seasonal-naive forecast after time aggregation.",
        "validation": ["Time-aware split", "Backtesting", "Compare to naive baseline"],
        "pitfalls": ["Random train/test split", "Future leakage", "Forecasting IDs"],
    },
    "clustering_or_segmentation": {
        "label": "Clustering / segmentation",
        "when": "There are multiple behavioral or numeric dimensions but no target.",
        "baseline": "Profile obvious business segments before unsupervised clustering.",
        "validation": ["Feature scaling", "Cluster stability", "Interpretability review"],
        "pitfalls": ["Clusters with no business action", "Distance dominated by one field"],
    },
    "anomaly_detection": {
        "label": "Anomaly detection",
        "when": "The user needs suspicious rows, outliers, or quality issues.",
        "baseline": "Z-score and robust threshold checks on meaningful numeric columns.",
        "validation": ["False positive review", "Known anomaly examples", "Feature sanity checks"],
        "pitfalls": ["Flagging legitimate large customers", "Using IDs as anomaly measures"],
    },
    "text_analysis": {
        "label": "Text analysis",
        "when": "There are free-text fields such as reviews, tickets, or comments.",
        "baseline": "Length, frequency, keyword, and topic inventory before embeddings.",
        "validation": ["Label quality", "Topic coherence", "Human review"],
        "pitfalls": ["Overinterpreting themes", "PII leakage"],
    },
    "not_enough_data": {
        "label": "Not enough data for ML",
        "when": "The data lacks a target, useful measures, or enough rows for the requested task.",
        "baseline": "Return descriptive findings and required next data.",
        "validation": ["State missing fields", "State unsupported claims"],
        "pitfalls": ["Forcing a model because the user asked for ML"],
    },
}


ID_LIKE_SUFFIXES = ("_id", "_key", "_uuid")
TARGET_HINTS = (
    "target",
    "label",
    "outcome",
    "status",
    "churn",
    "converted",
    "conversion",
    "return",
    "default",
    "fraud",
    "complete",
)
MEASURE_HINTS = (
    "revenue",
    "sales",
    "amount",
    "price",
    "cost",
    "margin",
    "quantity",
    "units",
    "score",
    "rate",
    "value",
)


def is_id_like(column_name: str) -> bool:
    normalized = column_name.lower().replace(" ", "_")
    return normalized in {"id", "uuid", "key"} or normalized.endswith(ID_LIKE_SUFFIXES)


def meaningful_numeric_columns(table: dict[str, Any]) -> list[str]:
    return [
        column
        for column in table.get("numeric_columns", [])
        if not is_id_like(column) and any(hint in column.lower() for hint in MEASURE_HINTS)
    ]


def target_candidates(table: dict[str, Any]) -> list[str]:
    candidates = []
    for column in table.get("columns", []):
        name = str(column.get("name", ""))
        if any(hint in name.lower() for hint in TARGET_HINTS):
            candidates.append(name)
    return candidates


def leakage_candidates(table: dict[str, Any]) -> list[str]:
    leakage_hints = ("future", "after", "post_", "predicted", "prediction", "probability", "score")
    return [
        str(column.get("name", ""))
        for column in table.get("columns", [])
        if any(hint in str(column.get("name", "")).lower() for hint in leakage_hints)
    ]


def choose_primary_method(profile: dict[str, Any], user_question: str) -> dict[str, Any]:
    """Choose a conservative primary method from data shape and user intent."""
    question = user_question.lower()
    tables = profile.get("tables", [])
    first_table = tables[0] if tables else {}
    meaningful_numeric = meaningful_numeric_columns(first_table)
    targets = target_candidates(first_table)
    date_columns = first_table.get("date_columns", [])
    categorical = first_table.get("categorical_columns", [])
    text = first_table.get("text_columns", [])
    row_count = int(first_table.get("row_count") or 0)

    if row_count < 30:
        return {
            "type": "not_enough_data",
            "confidence": "high",
            "reason": "The selected table is too small for reliable modeling.",
        }
    if any(token in question for token in ("forecast", "trend", "next month", "time series")):
        if date_columns and meaningful_numeric:
            return {
                "type": "forecasting",
                "confidence": "medium",
                "reason": "The user asked for a time-oriented answer and the data has a date plus meaningful numeric measures.",
            }
        if date_columns:
            return {
                "type": "descriptive_analysis",
                "confidence": "high",
                "reason": "The data has dates but no clear non-ID numeric measure, so trend counts are safer than forecasting.",
            }
    if any(token in question for token in ("predict", "classify", "churn", "conversion", "propensity")):
        if targets:
            return {
                "type": "classification_or_group_comparison",
                "confidence": "medium",
                "reason": f"Potential target fields detected: {', '.join(targets[:3])}.",
            }
        return {
            "type": "not_enough_data",
            "confidence": "medium",
            "reason": "The user asked for prediction, but no clear target column was detected.",
        }
    if any(token in question for token in ("driver", "drive", "why", "explain", "impact")):
        if meaningful_numeric and (categorical or len(meaningful_numeric) >= 2):
            return {
                "type": "regression_or_drivers",
                "confidence": "medium",
                "reason": "There are meaningful measures and grouping fields for driver exploration.",
            }
    if any(token in question for token in ("segment", "cluster", "persona")):
        if len(categorical) >= 2 or len(meaningful_numeric) >= 2:
            return {
                "type": "clustering_or_segmentation",
                "confidence": "medium",
                "reason": "There are multiple dimensions that can support exploratory segmentation.",
            }
    if any(token in question for token in ("anomaly", "outlier", "suspicious", "weird")):
        if meaningful_numeric:
            return {
                "type": "anomaly_detection",
                "confidence": "medium",
                "reason": "Meaningful numeric measures are available for outlier scans.",
            }
    if any(token in question for token in ("text", "comment", "review", "feedback", "topic")) and text:
        return {
            "type": "text_analysis",
            "confidence": "medium",
            "reason": "Free-text-like columns are present.",
        }
    if targets and meaningful_numeric:
        return {
            "type": "classification_or_group_comparison",
            "confidence": "low",
            "reason": "A target-like field and measures exist, but the business question should be clarified before modeling.",
        }
    return {
        "type": "descriptive_analysis",
        "confidence": "high",
        "reason": "A descriptive pass is the safest next step until the user selects a target, measure, or decision goal.",
    }


def method_details(method_type: str) -> dict[str, Any]:
    return METHOD_CATALOG.get(method_type, METHOD_CATALOG["descriptive_analysis"])
