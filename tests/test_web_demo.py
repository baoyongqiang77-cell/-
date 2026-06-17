import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web-demo"


class WebDemoTests(unittest.TestCase):
    def test_web_demo_files_exist(self):
        for relative in ["index.html", "styles.css", "app.js", "demo-data.js"]:
            self.assertTrue((WEB / relative).exists(), f"missing {relative}")

    def test_demo_data_contains_required_accounts_and_boundaries(self):
        data_js = (WEB / "demo-data.js").read_text(encoding="utf-8")
        match = re.search(r"window\.DEMO_DATA\s*=\s*(\{.*\});\s*$", data_js, re.S)
        self.assertIsNotNone(match, "demo-data.js must assign window.DEMO_DATA")
        data = json.loads(match.group(1))

        self.assertEqual(
            [account["username"] for account in data["accounts"]],
            ["platform_admin", "customer_flight", "customer_viewer", "customer_annotator"],
        )
        self.assertIn("模拟演示环境", data["environment"]["name"])
        self.assertIn("真实 DJI", data["environment"]["limitations"])
        self.assertEqual(len(data["units"]), 8)
        self.assertEqual(len(data["workflow"]), 7)
        self.assertEqual(len(data["algorithms"]), 14)
        self.assertEqual(data["algorithms"][0]["code"], "traffic_congestion")
        self.assertEqual(data["hardware"]["status"], "候选池")

    def test_index_contains_login_and_app_mount_points(self):
        html = (WEB / "index.html").read_text(encoding="utf-8")

        self.assertIn('id="login-view"', html)
        self.assertIn('id="app-view"', html)
        self.assertIn('id="account-list"', html)
        self.assertIn('id="main-panel"', html)
        self.assertIn("demo-data.js", html)
        self.assertIn("app.js", html)


if __name__ == "__main__":
    unittest.main()
