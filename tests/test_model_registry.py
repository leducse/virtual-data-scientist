from __future__ import annotations

import tempfile
import unittest

from model_registry.deal_risk import (
    audit_dataset,
    chronological_split,
    generate_deal_risk_dataset,
)
from model_registry.service import ModelRegistryService


class ModelRegistryTests(unittest.TestCase):
    def test_synthetic_dataset_is_point_in_time_and_chronologically_isolated(self) -> None:
        rows = generate_deal_risk_dataset()
        audit = audit_dataset(rows)
        train, test = chronological_split(rows)

        self.assertTrue(audit["ready"], audit)
        self.assertEqual(audit["records"], 360)
        self.assertLess(max(row["snapshot_date"] for row in train), min(row["snapshot_date"] for row in test))
        self.assertTrue({row["opportunity_id"] for row in train}.isdisjoint({row["opportunity_id"] for row in test}))

    def test_forbidden_post_outcome_feature_fails_the_audit(self) -> None:
        rows = generate_deal_risk_dataset(weeks=4)
        rows[0]["final_stage"] = "Closed Lost"
        audit = audit_dataset(rows)
        self.assertFalse(audit["ready"])
        self.assertEqual(audit["forbidden_features"], ["final_stage"])

    def test_evaluate_register_approve_and_batch_score_workflow(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = ModelRegistryService(temp_dir)
            result = service.train_baseline()
            candidate = result["comparison"]["logistic_regression_candidate"]
            baseline = result["comparison"]["constant_risk_baseline"]

            self.assertTrue(result["quality_gates"]["passed"], result)
            self.assertLess(candidate["brier_score"], baseline["brier_score"])
            self.assertGreater(candidate["average_precision"], baseline["average_precision"])
            self.assertLess(baseline["average_precision"], 1.0)
            self.assertEqual(result["registered_version"]["status"], "PendingReview")

            with self.assertRaisesRegex(ValueError, "ApprovedForDemo"):
                service.score_demo_batch(1)

            approved = service.approve(1)
            self.assertEqual(approved["approved_version"]["status"], "ApprovedForDemo")

            scored = service.score_demo_batch(1)
            self.assertEqual(scored["records"], 12)
            self.assertEqual(scored["model_version"], 1)
            self.assertEqual(len(scored["scores"][0]["reason_codes"]), 3)
            self.assertGreaterEqual(
                scored["scores"][0]["risk_probability"],
                scored["scores"][-1]["risk_probability"],
            )

            catalog = service.catalog()
            events = [event["event_type"] for event in catalog["audit_events"]]
            self.assertEqual(
                events,
                [
                    "model_version_registered",
                    "model_version_approved_for_demo",
                    "batch_scoring_completed",
                ],
            )


if __name__ == "__main__":
    unittest.main()
