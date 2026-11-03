"""Application service for the local sales-analytics model registry."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from model_registry.deal_risk import (
    audit_dataset,
    chronological_split,
    evaluate_constant_baseline,
    evaluate_model,
    explain_prediction,
    generate_deal_risk_dataset,
    predict_probability,
    scoring_rows,
    train_logistic_regression,
)
from model_registry.registry import LocalModelRegistry


JsonDict = dict[str, Any]
GROUP_NAME = "deal-risk-weekly"


class ModelRegistryService:
    """Coordinate dataset gates, evaluation, registration, approval, and scoring."""

    def __init__(self, data_dir: str | Path) -> None:
        self.data_dir = Path(data_dir)
        self.registry = LocalModelRegistry(self.data_dir / "model_registry.json")

    @staticmethod
    def use_case_card() -> JsonDict:
        return {
            "group_name": GROUP_NAME,
            "display_name": "Deal Risk — Weekly Snapshot",
            "feature_contract_version": "deal-risk-weekly-v1",
            "prediction_target": (
                "Open opportunity is lost or slips more than 30 days within the next 30 days."
            ),
            "intended_use": (
                "Prioritize a bounded analyst review queue using point-in-time synthetic data."
            ),
            "prohibited_uses": [
                "Automated personnel decisions",
                "Customer-facing eligibility or pricing decisions",
                "Scoring data that did not pass the feature contract",
                "Production use of this synthetic demonstration model",
            ],
            "execution_mode": "local_batch_demo",
        }

    def catalog(self) -> JsonDict:
        return {
            "ok": True,
            "use_cases": [self.use_case_card()],
            **self.registry.catalog(),
        }

    def train_baseline(self) -> JsonDict:
        rows = generate_deal_risk_dataset()
        dataset_audit = audit_dataset(rows)
        if not dataset_audit["ready"]:
            raise ValueError("Synthetic deal-risk data failed its point-in-time audit.")

        train_rows, test_rows = chronological_split(rows)
        model = train_logistic_regression(train_rows)
        naive_metrics = evaluate_constant_baseline(train_rows, test_rows)
        candidate_metrics = evaluate_model(model, test_rows)

        gate_checks = {
            "brier_improvement_at_least_0_015": (
                naive_metrics["brier_score"] - candidate_metrics["brier_score"] >= 0.015
            ),
            "average_precision_lift_at_least_0_10": (
                candidate_metrics["average_precision"] - naive_metrics["average_precision"] >= 0.10
            ),
            "top_10_percent_recall_at_least_0_15": (
                candidate_metrics["recall_at_top_10_percent"] >= 0.15
            ),
        }
        quality_gates = {
            "passed": all(gate_checks.values()),
            "checks": gate_checks,
            "note": "Passing creates a reviewable candidate; it does not auto-approve production use.",
        }
        comparison = {
            "constant_risk_baseline": naive_metrics,
            "logistic_regression_candidate": candidate_metrics,
            "brier_improvement": round(
                naive_metrics["brier_score"] - candidate_metrics["brier_score"],
                6,
            ),
            "average_precision_lift": round(
                candidate_metrics["average_precision"] - naive_metrics["average_precision"],
                6,
            ),
        }
        version = self.registry.register_version(
            group_name=GROUP_NAME,
            model_card=self.use_case_card(),
            artifact=model,
            metrics=comparison,
            quality_gates=quality_gates,
            lineage={
                "dataset": "deterministic_synthetic_deal_risk_v1",
                "dataset_seed": 42,
                "records": len(rows),
                "train_end": dataset_audit["split"]["train_end"],
                "test_start": dataset_audit["split"]["test_start"],
                "split_strategy": "chronological_snapshot_date",
                "feature_contract_version": "deal-risk-weekly-v1",
                "trainer": "model_registry.deal_risk.train_logistic_regression",
            },
        )
        return {
            "ok": True,
            "dataset_audit": dataset_audit,
            "comparison": comparison,
            "quality_gates": quality_gates,
            "registered_version": version,
            "decision_required": "Approve for demo or reject; do not tune yet.",
        }

    def approve(self, version_number: int) -> JsonDict:
        return {
            "ok": True,
            "approved_version": self.registry.approve_version(GROUP_NAME, version_number),
        }

    def score_demo_batch(self, version_number: int) -> JsonDict:
        version = self.registry.get_version(GROUP_NAME, version_number)
        if version["status"] != "ApprovedForDemo":
            raise ValueError("Batch scoring requires an ApprovedForDemo model version.")

        scored = []
        for row in scoring_rows():
            probability = predict_probability(version["artifact"], row)
            scored.append(
                {
                    "opportunity_id": row["opportunity_id"],
                    "snapshot_date": row["snapshot_date"],
                    "risk_probability": round(probability, 6),
                    "risk_band": (
                        "high" if probability >= 0.65 else "medium" if probability >= 0.35 else "low"
                    ),
                    "reason_codes": explain_prediction(version["artifact"], row),
                }
            )
        scored.sort(key=lambda row: row["risk_probability"], reverse=True)
        batch_id = f"score-{uuid.uuid4().hex[:10]}"
        self.registry.record_batch_score(
            group_name=GROUP_NAME,
            version_number=version_number,
            batch_id=batch_id,
            records=len(scored),
        )
        return {
            "ok": True,
            "batch_id": batch_id,
            "model_group": GROUP_NAME,
            "model_version": version_number,
            "feature_contract_version": version["lineage"]["feature_contract_version"],
            "records": len(scored),
            "scores": scored,
            "disclaimer": "Synthetic demonstration scores for analyst review only.",
        }
