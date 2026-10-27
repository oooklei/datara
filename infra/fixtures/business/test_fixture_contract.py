from pathlib import Path
import csv
import unittest


ROOT = Path(__file__).resolve().parent


class FixtureContractTest(unittest.TestCase):
    def test_source_contains_required_domains_and_stable_projection(self):
        sql = (ROOT / "sql" / "source.sql").read_text(encoding="utf-8")
        for table in ("dim_user", "dim_goods", "ods_order", "ods_order_item", "ods_payment"):
            self.assertIn(f"INSERT INTO {table}", sql)
        self.assertIn("CREATE OR REPLACE VIEW fixture_order_detail_source", sql)

    def test_target_has_actual_and_expected_baseline(self):
        sql = (ROOT / "sql" / "target.sql").read_text(encoding="utf-8")
        self.assertIn("fixture_order_detail_actual", sql)
        self.assertIn("fixture_order_detail_expected", sql)
        self.assertEqual(sql.count("'INFRA-DATA-01',9100000001"), 4)

    def test_file_sample_is_small_and_well_formed(self):
        sample = ROOT / "files" / "orders_file_sync.csv"
        with sample.open(encoding="utf-8", newline="") as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual(len(rows), 3)
        self.assertEqual(
            list(rows[0]),
            ["order_no", "user_name", "goods_name", "quantity", "unit_price", "order_status", "pay_channel", "order_date"],
        )
        self.assertEqual({row["order_status"] for row in rows}, {"PAID", "DONE", "CREATED"})

    def test_scripts_do_not_embed_sensitive_values(self):
        scripts = "\n".join((ROOT / name).read_text(encoding="utf-8") for name in ("common.sh", "check.sh", "prepare.sh", "verify.sh", "seed_product_fixture.py"))
        for forbidden in ("REBUILD_VALIDATION_KEY=", "DATARA_ACCESS_TOKEN=", "-pdatara_", "token: "):
            self.assertNotIn(forbidden, scripts)
        self.assertIn('$MYSQL_ROOT_PASSWORD', scripts)

    def test_api_entry_points_are_documented(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        for path in ("/api/v1/rebuild/validation-token", "/api/v1/rebuild/projects", "/api/v1/rebuild/variables"):
            self.assertIn(path, readme)
        self.assertIn("baseMode=file_sync", readme)
        self.assertIn("filePath=/datara/files/fixtures/orders_file_sync.csv", readme)
        self.assertIn("fileType=csv", readme)
        self.assertNotIn("/api/v1/rebuild/resources/uploads", readme)


if __name__ == "__main__":
    unittest.main()
