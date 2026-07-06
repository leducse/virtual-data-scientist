import io
import os
import tempfile
import time
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

import server


class FakeS3NotFound(Exception):
    def __init__(self) -> None:
        super().__init__("NoSuchKey")
        self.response = {"Error": {"Code": "NoSuchKey"}}


class FakeS3Client:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}

    def put_object(self, Bucket: str, Key: str, Body: bytes, **_: Any) -> None:
        self.objects[(Bucket, Key)] = Body

    def get_object(self, Bucket: str, Key: str) -> dict[str, Any]:
        if (Bucket, Key) not in self.objects:
            raise FakeS3NotFound()
        return {"Body": io.BytesIO(self.objects[(Bucket, Key)])}


class FakeBoto3:
    def __init__(self, client: FakeS3Client) -> None:
        self._client = client

    def client(self, service_name: str, **_: Any) -> FakeS3Client:
        if service_name != "s3":
            raise ValueError(f"Unexpected fake service: {service_name}")
        return self._client


class AnalysisPersistenceTest(unittest.TestCase):
    def setUp(self) -> None:
        server.initialize_demo_database()
        self.tempdir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.tempdir.name)
        self.original_analysis_path = server.ANALYSIS_PATH
        self.original_artifact_dir = server.ANALYSIS_ARTIFACT_DIR
        self.active_deep_run_id: str | None = None

        server.ANALYSIS_PATH = self.temp_path / "analysis_sessions.json"
        server.ANALYSIS_ARTIFACT_DIR = self.temp_path / "analysis_artifacts"
        server.ANALYSIS_ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        if self.active_deep_run_id:
            self.wait_for_run(self.active_deep_run_id)
        server.ANALYSIS_PATH = self.original_analysis_path
        server.ANALYSIS_ARTIFACT_DIR = self.original_artifact_dir
        self.tempdir.cleanup()

    def wait_for_run(self, run_id: str) -> dict[str, Any]:
        status = server.get_analysis_status(run_id)
        deadline = time.time() + 5
        while status["run"]["status"] in {"queued", "running"} and time.time() < deadline:
            time.sleep(0.05)
            status = server.get_analysis_status(run_id)
        self.assertEqual(status["run"]["status"], "succeeded")
        return status

    def test_session_followup_and_artifacts_persist_across_calls(self) -> None:
        created = server.create_analysis_session(
            {
                "user_goal": "Profile this sales dataset and recommend next analysis steps.",
                "data_source_id": "demo_warehouse",
                "table_name": "orders",
            }
        )
        session_id = created["session"]["id"]

        light = server.run_light_analysis(
            {
                "session_id": session_id,
                "user_question": "What can I learn from this orders table?",
                "data_source_id": "demo_warehouse",
                "table_name": "orders",
            }
        )
        followup = server.continue_analysis(
            {
                "session_id": session_id,
                "message": "Now compare this with customer and product context.",
            }
        )

        reloaded = server.read_analysis_doc()
        session = server.find_record(reloaded, "sessions", session_id)
        messages = [message for message in reloaded["messages"] if message["session_id"] == session_id]
        run_ids = {run["id"] for run in reloaded["runs"] if run["session_id"] == session_id}
        artifacts = [artifact for artifact in reloaded["artifacts"] if artifact["run_id"] in run_ids]

        self.assertEqual(session["current_dataset_id"], light["dataset"]["id"])
        self.assertEqual(session["data_source_id"], "demo_warehouse")
        self.assertEqual(followup["run_count"], 1)
        self.assertGreaterEqual(len(messages), 3)
        self.assertEqual({artifact["artifact_type"] for artifact in artifacts}, {"profile", "code", "report"})
        self.assertTrue(server.ANALYSIS_PATH.exists())
        self.assertEqual(len(list(server.ANALYSIS_ARTIFACT_DIR.iterdir())), 3)
        self.assertTrue(all("content" not in artifact for artifact in followup["artifacts"]))

    def test_s3_csv_upload_persists_source_and_schema(self) -> None:
        fake_s3 = FakeS3Client()
        with mock.patch.object(server, "boto3", FakeBoto3(fake_s3)), mock.patch.dict(
            os.environ,
            {
                "ANALYSIS_STORAGE": "s3",
                "ANALYSIS_STATE_BUCKET": "unit-test-bucket",
                "ANALYSIS_STATE_PREFIX": "unit-test-vds",
            },
        ):
            result = server.upload_csv_dataset(
                "Churn Sample",
                "customer_id,churn,monthly_fee\n1,0,99.50\n2,1,49.00\n3,0,79.00\n",
            )

            self.assertTrue(result["ok"])
            self.assertTrue(result["data_source_id"].startswith("csv_"))
            self.assertEqual(result["source"]["type"], "s3_csv")
            self.assertEqual(result["source"]["persisted"], True)
            self.assertEqual(result["row_count"], 3)
            self.assertTrue(result["s3"]["uri"].startswith("s3://unit-test-bucket/unit-test-vds/uploads/"))

            persisted = server.read_analysis_doc()
            self.assertEqual(persisted["data_sources"][0]["id"], result["data_source_id"])

            schema = server.get_schema(result["data_source_id"])
            self.assertEqual(schema["active_data_source_id"], result["data_source_id"])
            self.assertEqual(schema["tables"][0]["name"], result["table_name"])
            self.assertEqual(schema["tables"][0]["row_count"], 3)

            light = server.run_light_analysis(
                {
                    "user_question": "What analysis should I run for churn?",
                    "data_source_id": result["data_source_id"],
                    "table_name": result["table_name"],
                }
            )
            self.assertEqual(light["dataset"]["data_source_id"], result["data_source_id"])
            self.assertEqual(light["dataset"]["storage_uri"], result["s3"]["uri"])

    def test_deep_analysis_persists_context_bundle_report_and_code(self) -> None:
        created = server.create_analysis_session(
            {
                "user_goal": "Run deeper analysis on customer revenue patterns.",
                "data_source_id": "demo_warehouse",
                "table_name": "orders",
            }
        )
        session_id = created["session"]["id"]
        light = server.run_light_analysis(
            {
                "session_id": session_id,
                "user_question": "Which method should I use first?",
                "data_source_id": "demo_warehouse",
                "table_name": "orders",
            }
        )
        light_artifact_ids = {artifact["artifact_type"]: artifact["id"] for artifact in light["artifacts"]}

        queued = server.request_deep_analysis(
            {
                "session_id": session_id,
                "user_question": "Run a deep method-selection pass and preserve the code.",
                "constraints": {
                    "max_runtime_minutes": 3,
                    "privacy_mode": "registered_dataset_only",
                },
            }
        )
        self.active_deep_run_id = queued["run"]["id"]
        status = self.wait_for_run(self.active_deep_run_id)

        context = queued["context_bundle"]
        self.assertEqual(context["session_id"], session_id)
        self.assertEqual(context["dataset_id"], light["dataset"]["id"])
        self.assertEqual(context["schema_profile_id"], light_artifact_ids["profile"])
        self.assertEqual(context["light_analysis_code_id"], light_artifact_ids["code"])
        self.assertEqual(context["light_analysis_report_id"], light_artifact_ids["report"])
        self.assertEqual(context["constraints"]["privacy_mode"], "registered_dataset_only")
        self.assertEqual(context["constraints"]["agentcore_mode"], "local_worker")

        artifact_types = [artifact["artifact_type"] for artifact in status["artifacts"]]
        self.assertEqual(artifact_types, ["context_bundle", "report", "code"])
        report = next(artifact for artifact in status["artifacts"] if artifact["artifact_type"] == "report")
        code = next(artifact for artifact in status["artifacts"] if artifact["artifact_type"] == "code")
        self.assertIsInstance(report["content"], dict)
        self.assertIn("summary", report["content"])
        self.assertIsInstance(code["content"], str)
        self.assertIn("PRIMARY_METHOD", code["content"])
        self.assertIn("def main", code["content"])

        listed = server.list_analysis_sessions()
        listed_artifacts = [artifact for artifact in listed["artifacts"] if artifact["run_id"] == self.active_deep_run_id]
        self.assertEqual({artifact["artifact_type"] for artifact in listed_artifacts}, {"context_bundle", "report", "code"})
        self.assertTrue(all("content" not in artifact for artifact in listed_artifacts))
        self.assertTrue(all("/" not in artifact["storage_uri"] for artifact in listed_artifacts))

        detail = server.get_analysis_session_detail(session_id)
        self.assertEqual(detail["session"]["id"], session_id)
        self.assertEqual(detail["dataset"]["id"], light["dataset"]["id"])
        self.assertGreaterEqual(len(detail["messages"]), 4)
        self.assertEqual({artifact["artifact_type"] for artifact in detail["artifacts"]}, {
            "profile",
            "code",
            "report",
            "context_bundle",
        })
        self.assertTrue(all("content" not in artifact for artifact in detail["artifacts"]))
        self.assertTrue(all("/" not in artifact["storage_uri"] for artifact in detail["artifacts"]))


if __name__ == "__main__":
    unittest.main()
