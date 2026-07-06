import unittest
import uuid

import server
from analysis_engine.deep_worker import run_local_deep_analysis


class DeepWorkerDiagnosticsTest(unittest.TestCase):
    def setUp(self) -> None:
        server.initialize_demo_database()
        self.created_tables: list[str] = []

    def tearDown(self) -> None:
        if not self.created_tables:
            return
        con = server.connect_db()
        try:
            for table_name in self.created_tables:
                con.execute(f'DROP TABLE IF EXISTS "{table_name}"')
            con.commit()
        finally:
            con.close()

    def create_table(self, table_name: str, ddl: str, rows: list[tuple]) -> None:
        self.created_tables.append(table_name)
        con = server.connect_db()
        try:
            con.execute(ddl)
            placeholders = ", ".join("?" for _ in rows[0])
            con.executemany(f'INSERT INTO "{table_name}" VALUES ({placeholders})', rows)
            con.commit()
        finally:
            con.close()

    def test_forecasting_diagnostics_include_naive_baseline(self) -> None:
        table_name = f"test_forecast_{uuid.uuid4().hex[:8]}"
        rows = []
        for month in range(1, 7):
            for day in range(1, 7):
                rows.append((f"2026-{month:02d}-{day:02d}", 100 + month * 10 + day, "direct" if day % 2 else "partner"))
        self.create_table(
            table_name,
            f'''
            CREATE TABLE "{table_name}" (
              sale_date TEXT,
              revenue REAL,
              channel TEXT
            )
            ''',
            rows,
        )

        profile = server.build_light_profile("demo_warehouse", table_name, "Forecast revenue for the next month.")
        result = run_local_deep_analysis(
            context_bundle={"user_question": "Forecast revenue for the next month."},
            profile=profile,
            db_path=server.DB_PATH,
        )
        report = result["report"]
        forecast = report["baseline_diagnostics"]["forecasting"]

        self.assertEqual(report["primary_method"]["type"], "forecasting")
        self.assertEqual(forecast["date_column"], "sale_date")
        self.assertEqual(forecast["measure_column"], "revenue")
        self.assertEqual(forecast["period_count"], 6)
        self.assertIsNotNone(forecast["naive_mae"])
        self.assertEqual(len(forecast["periods"]), 6)

    def test_classification_diagnostics_include_class_balance_and_group_summary(self) -> None:
        table_name = f"test_churn_{uuid.uuid4().hex[:8]}"
        rows = []
        for index in range(40):
            churn_status = "churned" if index % 4 == 0 else "retained"
            rows.append((churn_status, 50 + index * 3, "enterprise" if index % 3 == 0 else "self_serve"))
        self.create_table(
            table_name,
            f'''
            CREATE TABLE "{table_name}" (
              churn_status TEXT,
              revenue REAL,
              segment TEXT
            )
            ''',
            rows,
        )

        profile = server.build_light_profile("demo_warehouse", table_name, "Predict customer churn.")
        result = run_local_deep_analysis(
            context_bundle={"user_question": "Predict customer churn."},
            profile=profile,
            db_path=server.DB_PATH,
        )
        report = result["report"]
        diagnostics = report["baseline_diagnostics"]

        self.assertEqual(report["primary_method"]["type"], "classification_or_group_comparison")
        self.assertEqual(diagnostics["classification"]["target_column"], "churn_status")
        self.assertEqual(diagnostics["classification"]["class_count"], 2)
        self.assertEqual(diagnostics["classification"]["majority_baseline_accuracy_pct"], 75.0)
        self.assertTrue(diagnostics["group_measure_summary"])


if __name__ == "__main__":
    unittest.main()
