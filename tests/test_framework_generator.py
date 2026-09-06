import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

from reporting.snapshot_mvp import COLUMNS


ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "spreadsheet_build/build_seo_geo_reporting_framework_v1.mjs"
LEGACY_HEADERS = [
    "Snapshot ID", "載入時間", "資料來源", "報表粒度", "期間起日", "期間迄日",
    "As-of 日期", "資料狀態", "Metric Group", "Metric", "Segment", "Platform / Property",
    "Value", "Denominator", "Target", "正式來源", "原始檔 / 查詢連結", "Revision / Note",
]


def node_executable():
    path_node = shutil.which("node")
    if path_node:
        return path_node
    bundled = Path(sys.executable).absolute().parents[2] / "node/bin/node"
    if bundled.is_file():
        return str(bundled)
    raise RuntimeError("Node.js is required to validate the framework generator manifest")


def generator_manifest():
    result = subprocess.run(
        [node_executable(), str(GENERATOR), "--snapshot-schema-manifest"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


class FrameworkGeneratorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = generator_manifest()

    def test_legacy_and_v2_snapshot_sheets_exist(self):
        self.assertEqual(self.manifest["legacy"]["sheetName"], "KPI Snapshots")
        self.assertEqual(self.manifest["v2"]["sheetName"], "KPI Snapshots v2")

    def test_legacy_schema_remains_unchanged(self):
        self.assertEqual(self.manifest["legacy"]["headers"], LEGACY_HEADERS)

    def test_v2_header_uses_authoritative_contract_columns(self):
        self.assertEqual(self.manifest["v2"]["headers"], COLUMNS)
        self.assertEqual(len(self.manifest["v2"]["headers"]), 25)

    def test_v2_layout_and_default_data_area(self):
        v2 = self.manifest["v2"]
        self.assertEqual(v2["headerRow"], 4)
        self.assertEqual(v2["initialDataRows"], [])
        self.assertEqual(v2["title"], "KPI Snapshots v2｜Append-only Data Contract v1.0")
        self.assertEqual(
            v2["description"],
            "Production snapshot storage after activation. Activation pending until programmatic gateway verification. Legacy KPI Snapshots remains historical/read-only. No raw personal data.",
        )
