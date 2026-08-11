import re
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
WORKFLOW_PATH = PROJECT_ROOT / ".github" / "workflows" / "forward_radar_monthly.yml"
WEEKLY_WORKFLOW_PATH = PROJECT_ROOT / ".github" / "workflows" / "weekly.yml"


class ForwardRadarWorkflowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
        cls.weekly_workflow = WEEKLY_WORKFLOW_PATH.read_text(encoding="utf-8")

    def test_workflow_exists_with_valid_static_structure(self):
        self.assertTrue(WORKFLOW_PATH.is_file())
        self.assertNotIn("\t", self.workflow)
        self.assertEqual(self.workflow.count("${{"), self.workflow.count("}}"))
        self.assertNotRegex(self.workflow, r"^\s{1,1}\S", re.MULTILINE)
        self.assertIn("name: 每月國際捷運前瞻技術雷達", self.workflow)
        self.assertIn("jobs:\n  generate-forward-radar:", self.workflow)

    def test_monthly_schedule_and_manual_dispatch(self):
        self.assertIn("cron: '17 1 1 * *'", self.workflow)
        self.assertIn("workflow_dispatch:", self.workflow)

    def test_runtime_and_radar_command_are_fixed(self):
        self.assertIn("runs-on: ubuntu-latest", self.workflow)
        self.assertIn("actions/checkout@v4", self.workflow)
        self.assertIn("actions/setup-python@v5", self.workflow)
        self.assertIn("python-version: '3.11'", self.workflow)
        self.assertIn("pip install -r requirements.txt", self.workflow)
        self.assertIn(
            "python -u forward_radar_main.py --lookback-days 30 --output-dir output",
            self.workflow,
        )
        self.assertNotIn("python -u main.py", self.workflow)

    def test_artifact_configuration(self):
        self.assertIn("actions/upload-artifact@v4", self.workflow)
        self.assertIn("name: forward-technology-radar-${{ github.run_id }}", self.workflow)
        self.assertIn("output/forward_radar_*.md", self.workflow)
        self.assertIn("output/forward_radar_*.json", self.workflow)
        self.assertIn("retention-days: 90", self.workflow)

    def test_permissions_timeout_and_concurrency_are_minimal(self):
        self.assertIn("permissions:\n  contents: read", self.workflow)
        self.assertIn("timeout-minutes: 20", self.workflow)
        self.assertIn("group: forward-radar-monthly", self.workflow)
        self.assertIn("cancel-in-progress: false", self.workflow)

    def test_no_report_secrets_or_external_report_services(self):
        forbidden = (
            "MAIAGENT_API_KEY",
            "MAIAGENT_CHATBOT_ID",
            "MAIAGENT_API_BASE",
            "GMAIL_USER",
            "GMAIL_APP_PASS",
            "RECIPIENTS",
            "SMTP",
            "MaiAgent",
            "maiagent",
        )
        for value in forbidden:
            self.assertNotIn(value, self.workflow)

    def test_weekly_workflow_is_unchanged_and_separate(self):
        self.assertIn("python -u main.py", self.weekly_workflow)
        self.assertNotIn("forward_radar_main.py", self.weekly_workflow)
        self.assertNotIn("include_forward_technology=True", self.weekly_workflow)


if __name__ == "__main__":
    unittest.main()
