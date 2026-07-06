import unittest
import uuid

import server


class AnalysisMethodSelectionTest(unittest.TestCase):
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

    def test_order_table_does_not_treat_ids_as_business_measures(self) -> None:
        profile = server.build_light_profile(
            "demo_warehouse",
            "orders",
            "Should I forecast sales?",
        )
        table = profile["tables"][0]
        method_types = [method["type"] for method in table["candidate_methods"]]

        self.assertEqual(table["meaningful_numeric_columns"], [])
        self.assertEqual(method_types[0], "descriptive_analysis")
        self.assertNotIn("forecasting", method_types)
        self.assertNotIn("regression_or_drivers", method_types)

    def test_revenue_table_still_recommends_measure_based_methods(self) -> None:
        table_name = f"test_revenue_{uuid.uuid4().hex[:8]}"
        self.created_tables.append(table_name)
        con = server.connect_db()
        try:
            con.execute(
                f'''
                CREATE TABLE "{table_name}" (
                  customer_id INTEGER,
                  signup_date TEXT,
                  revenue REAL,
                  status TEXT
                )
                '''
            )
            con.executemany(
                f'INSERT INTO "{table_name}" VALUES (?, ?, ?, ?)',
                [
                    (1, "2026-01-01", 120.50, "active"),
                    (2, "2026-01-03", 80.00, "churned"),
                    (3, "2026-01-05", 220.10, "active"),
                    (4, "2026-01-09", 15.75, "trial"),
                ],
            )
            con.commit()
        finally:
            con.close()

        profile = server.build_light_profile(
            "demo_warehouse",
            table_name,
            "What should I run on this customer revenue data?",
        )
        table = profile["tables"][0]
        method_types = [method["type"] for method in table["candidate_methods"]]

        self.assertEqual(table["meaningful_numeric_columns"], ["revenue"])
        self.assertIn("forecasting", method_types)
        self.assertIn("regression_or_drivers", method_types)
        self.assertIn("anomaly_detection", method_types)


if __name__ == "__main__":
    unittest.main()
