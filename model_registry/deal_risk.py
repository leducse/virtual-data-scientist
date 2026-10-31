"""Deterministic deal-risk data, baseline training, and evaluation.

This module deliberately implements a small logistic regression with the Python
standard library. The goal is not to replace scikit-learn. It makes every step
of the evaluate-first POC inspectable: point-in-time data generation,
standardization learned on the training partition, gradient descent, probability
calibration, chronological evaluation, and per-row reason codes.
"""

from __future__ import annotations

import datetime as dt
import math
import random
from typing import Any, Iterable


JsonDict = dict[str, Any]

FEATURE_NAMES = [
    "stage_progress",
    "log_amount",
    "age_days",
    "days_in_current_stage",
    "days_until_stated_close",
    "close_date_change_count_30d",
    "activity_count_14d",
    "days_since_last_activity",
    "coverage_role_count",
    "product_usage_trend_28d",
]

FEATURE_LABELS = {
    "stage_progress": "sales stage progression",
    "log_amount": "deal amount",
    "age_days": "opportunity age",
    "days_in_current_stage": "time in current stage",
    "days_until_stated_close": "time until stated close",
    "close_date_change_count_30d": "recent close-date changes",
    "activity_count_14d": "recent team activity",
    "days_since_last_activity": "time since last activity",
    "coverage_role_count": "team coverage",
    "product_usage_trend_28d": "recent service-usage trend",
}

FORBIDDEN_FEATURES = {
    "actual_close_date",
    "closed_lost_reason_entered_after_snapshot",
    "final_stage",
}


def _sigmoid(value: float) -> float:
    # Clipping avoids overflow while preserving probabilities at any scale the
    # small teaching model can produce.
    bounded = max(-35.0, min(35.0, value))
    return 1.0 / (1.0 + math.exp(-bounded))


def generate_deal_risk_dataset(
    *,
    seed: int = 42,
    weeks: int = 60,
    records_per_week: int = 6,
    start_date: dt.date = dt.date(2025, 1, 6),
) -> list[JsonDict]:
    """Create synthetic point-in-time opportunity snapshots.

    Every opportunity appears once, so an opportunity ID cannot leak across the
    chronological split. A mild late-period shift makes the holdout more useful
    than an identically distributed random sample.
    """

    rng = random.Random(seed)
    rows: list[JsonDict] = []
    for week in range(weeks):
        snapshot_date = start_date + dt.timedelta(days=7 * week)
        for slot in range(records_per_week):
            stage_progress = rng.randint(1, 5)
            amount = round(math.exp(rng.uniform(math.log(8_000), math.log(900_000))), 2)
            age_days = rng.randint(7, 320)
            days_in_stage = rng.randint(1, min(100, age_days))
            days_until_close = rng.randint(-25, 150)
            close_changes = min(5, int(rng.expovariate(0.9)))
            activity_count = rng.randint(0, 22)
            days_since_activity = rng.randint(0, 50)
            coverage_count = rng.randint(1, 5)
            usage_trend = round(rng.uniform(-0.65, 0.8), 3)

            # The hidden data-generating process is intentionally interpretable:
            # inactivity, stalled stages, and close-date churn raise risk;
            # activity, coverage, and positive usage lower it.
            risk_logit = (
                -1.65
                + 0.018 * days_in_stage
                + 0.52 * close_changes
                + 0.032 * days_since_activity
                - 0.065 * activity_count
                - 0.24 * coverage_count
                - 1.15 * usage_trend
                - 0.12 * stage_progress
                + 0.003 * max(-days_until_close, 0)
                + rng.normalvariate(0, 0.45)
            )
            if week >= int(weeks * 0.75):
                # Late snapshots are slightly riskier, mimicking a modest
                # temporal shift rather than a perfectly stationary dataset.
                risk_logit += 0.18

            rows.append(
                {
                    "opportunity_id": f"opp-{week:03d}-{slot:02d}",
                    "snapshot_date": snapshot_date.isoformat(),
                    "stage_progress": float(stage_progress),
                    "log_amount": round(math.log1p(amount), 6),
                    "age_days": float(age_days),
                    "days_in_current_stage": float(days_in_stage),
                    "days_until_stated_close": float(days_until_close),
                    "close_date_change_count_30d": float(close_changes),
                    "activity_count_14d": float(activity_count),
                    "days_since_last_activity": float(days_since_activity),
                    "coverage_role_count": float(coverage_count),
                    "product_usage_trend_28d": usage_trend,
                    "lost_or_slipped_30d": int(rng.random() < _sigmoid(risk_logit)),
                }
            )
    return rows


def chronological_split(
    rows: list[JsonDict],
    *,
    train_fraction: float = 0.75,
) -> tuple[list[JsonDict], list[JsonDict]]:
    """Split at a date boundary so no snapshot date occurs in both partitions."""

    dates = sorted({str(row["snapshot_date"]) for row in rows})
    cutoff_index = max(1, min(len(dates) - 1, int(len(dates) * train_fraction)))
    test_start = dates[cutoff_index]
    train = [row for row in rows if str(row["snapshot_date"]) < test_start]
    test = [row for row in rows if str(row["snapshot_date"]) >= test_start]
    return train, test


def audit_dataset(rows: list[JsonDict]) -> JsonDict:
    """Check the point-in-time feature and label contract before modeling."""

    required = {"opportunity_id", "snapshot_date", "lost_or_slipped_30d", *FEATURE_NAMES}
    missing_by_row = [
        index for index, row in enumerate(rows) if required.difference(row)
    ]
    forbidden_found = sorted(
        {key for row in rows for key in row if key in FORBIDDEN_FEATURES}
    )
    duplicate_ids = len(rows) - len({str(row.get("opportunity_id")) for row in rows})
    invalid_labels = sum(
        row.get("lost_or_slipped_30d") not in {0, 1} for row in rows
    )
    non_numeric_features = sum(
        not isinstance(row.get(feature), (int, float))
        for row in rows
        for feature in FEATURE_NAMES
    )
    train, test = chronological_split(rows)
    train_dates = [str(row["snapshot_date"]) for row in train]
    test_dates = [str(row["snapshot_date"]) for row in test]
    temporal_isolation = bool(train_dates and test_dates and max(train_dates) < min(test_dates))
    ready = not any(
        [missing_by_row, forbidden_found, duplicate_ids, invalid_labels, non_numeric_features]
    ) and temporal_isolation
    return {
        "ready": ready,
        "records": len(rows),
        "positive_rate": round(
            sum(int(row["lost_or_slipped_30d"]) for row in rows) / max(len(rows), 1),
            6,
        ),
        "feature_contract_version": "deal-risk-weekly-v1",
        "missing_row_count": len(missing_by_row),
        "forbidden_features": forbidden_found,
        "duplicate_opportunity_ids": duplicate_ids,
        "invalid_labels": invalid_labels,
        "non_numeric_feature_values": non_numeric_features,
        "split": {
            "strategy": "chronological_snapshot_date",
            "train_records": len(train),
            "test_records": len(test),
            "train_end": max(train_dates) if train_dates else None,
            "test_start": min(test_dates) if test_dates else None,
            "temporally_isolated": temporal_isolation,
        },
    }


def train_logistic_regression(
    rows: list[JsonDict],
    *,
    iterations: int = 900,
    learning_rate: float = 0.08,
    l2: float = 0.002,
) -> JsonDict:
    """Fit a standardized binary logistic model with batch gradient descent."""

    if not rows:
        raise ValueError("Training rows are required.")
    means = {
        feature: sum(float(row[feature]) for row in rows) / len(rows)
        for feature in FEATURE_NAMES
    }
    scales: dict[str, float] = {}
    for feature in FEATURE_NAMES:
        variance = sum(
            (float(row[feature]) - means[feature]) ** 2 for row in rows
        ) / len(rows)
        scales[feature] = max(math.sqrt(variance), 1e-9)

    matrix = [
        [(float(row[feature]) - means[feature]) / scales[feature] for feature in FEATURE_NAMES]
        for row in rows
    ]
    labels = [int(row["lost_or_slipped_30d"]) for row in rows]
    coefficients = [0.0] * len(FEATURE_NAMES)
    positive_rate = sum(labels) / len(labels)
    intercept = math.log((positive_rate + 1e-6) / (1 - positive_rate + 1e-6))

    for _ in range(iterations):
        coefficient_gradients = [0.0] * len(coefficients)
        intercept_gradient = 0.0
        for features, label in zip(matrix, labels, strict=True):
            probability = _sigmoid(
                intercept
                + sum(weight * value for weight, value in zip(coefficients, features, strict=True))
            )
            error = probability - label
            intercept_gradient += error
            for index, value in enumerate(features):
                coefficient_gradients[index] += error * value

        sample_count = len(rows)
        intercept -= learning_rate * intercept_gradient / sample_count
        coefficients = [
            weight
            - learning_rate
            * (coefficient_gradients[index] / sample_count + l2 * weight)
            for index, weight in enumerate(coefficients)
        ]

    return {
        "model_type": "standardized_logistic_regression",
        "feature_names": list(FEATURE_NAMES),
        "means": means,
        "scales": scales,
        "coefficients": coefficients,
        "intercept": intercept,
        "training": {
            "iterations": iterations,
            "learning_rate": learning_rate,
            "l2": l2,
            "training_records": len(rows),
        },
    }


def predict_probability(model: JsonDict, row: JsonDict) -> float:
    values = []
    for feature in model["feature_names"]:
        if feature not in row:
            raise ValueError(f"Missing required feature: {feature}")
        value = row[feature]
        if not isinstance(value, (int, float)):
            raise ValueError(f"Feature must be numeric: {feature}")
        values.append((float(value) - model["means"][feature]) / model["scales"][feature])
    logit = float(model["intercept"]) + sum(
        float(weight) * value
        for weight, value in zip(model["coefficients"], values, strict=True)
    )
    return _sigmoid(logit)


def _average_precision(labels: list[int], probabilities: list[float]) -> float:
    # Sort only by probability. Sorting `(probability, label)` tuples would use
    # the label as a hidden tie-breaker and make a constant predictor look
    # perfect—an instructive example of how metric implementations can leak the
    # answer key.
    ranked_indices = sorted(
        range(len(labels)),
        key=lambda index: probabilities[index],
        reverse=True,
    )
    positives = sum(labels)
    if not positives:
        return 0.0
    found = 0
    precision_sum = 0.0
    for rank, index in enumerate(ranked_indices, start=1):
        label = labels[index]
        if label:
            found += 1
            precision_sum += found / rank
    return precision_sum / positives


def _recall_at_fraction(
    labels: list[int],
    probabilities: list[float],
    fraction: float,
) -> float:
    positives = sum(labels)
    if not positives:
        return 0.0
    reviewed = max(1, math.ceil(len(labels) * fraction))
    ranked_labels = [
        labels[index]
        for index in sorted(
            range(len(labels)),
            key=lambda index: probabilities[index],
            reverse=True,
        )
    ]
    return sum(ranked_labels[:reviewed]) / positives


def binary_metrics(labels: list[int], probabilities: list[float]) -> JsonDict:
    predictions = [int(probability >= 0.5) for probability in probabilities]
    true_positive = sum(prediction == 1 and label == 1 for prediction, label in zip(predictions, labels, strict=True))
    false_positive = sum(prediction == 1 and label == 0 for prediction, label in zip(predictions, labels, strict=True))
    false_negative = sum(prediction == 0 and label == 1 for prediction, label in zip(predictions, labels, strict=True))
    correct = sum(prediction == label for prediction, label in zip(predictions, labels, strict=True))
    return {
        "records": len(labels),
        "positive_rate": round(sum(labels) / max(len(labels), 1), 6),
        "accuracy": round(correct / max(len(labels), 1), 6),
        "precision": round(true_positive / max(true_positive + false_positive, 1), 6),
        "recall": round(true_positive / max(true_positive + false_negative, 1), 6),
        "brier_score": round(
            sum((probability - label) ** 2 for probability, label in zip(probabilities, labels, strict=True))
            / max(len(labels), 1),
            6,
        ),
        "average_precision": round(_average_precision(labels, probabilities), 6),
        "recall_at_top_10_percent": round(
            _recall_at_fraction(labels, probabilities, 0.10),
            6,
        ),
    }


def evaluate_model(model: JsonDict, rows: list[JsonDict]) -> JsonDict:
    labels = [int(row["lost_or_slipped_30d"]) for row in rows]
    return binary_metrics(labels, [predict_probability(model, row) for row in rows])


def evaluate_constant_baseline(train_rows: list[JsonDict], test_rows: list[JsonDict]) -> JsonDict:
    constant_probability = sum(
        int(row["lost_or_slipped_30d"]) for row in train_rows
    ) / len(train_rows)
    metrics = binary_metrics(
        [int(row["lost_or_slipped_30d"]) for row in test_rows],
        [constant_probability] * len(test_rows),
    )
    metrics["constant_probability"] = round(constant_probability, 6)
    return metrics


def explain_prediction(model: JsonDict, row: JsonDict, *, limit: int = 3) -> list[JsonDict]:
    """Return the largest standardized linear contributions as reason codes."""

    contributions = []
    for feature, coefficient in zip(
        model["feature_names"],
        model["coefficients"],
        strict=True,
    ):
        standardized = (float(row[feature]) - model["means"][feature]) / model["scales"][feature]
        contribution = float(coefficient) * standardized
        contributions.append(
            {
                "feature": feature,
                "label": FEATURE_LABELS.get(feature, feature),
                "effect": "raises_risk" if contribution > 0 else "lowers_risk",
                "contribution": round(contribution, 6),
            }
        )
    return sorted(contributions, key=lambda item: abs(item["contribution"]), reverse=True)[:limit]


def scoring_rows(*, seed: int = 314) -> list[JsonDict]:
    """Create a small future batch with labels removed from the scoring input."""

    rows = generate_deal_risk_dataset(
        seed=seed,
        weeks=2,
        records_per_week=6,
        start_date=dt.date(2026, 7, 6),
    )
    return [
        {key: value for key, value in row.items() if key != "lost_or_slipped_30d"}
        for row in rows
    ]
