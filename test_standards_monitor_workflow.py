import re
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
WORKFLOW_PATH = PROJECT_ROOT / ".github" / "workflows" / "standards_monthly.yml"
WEEKLY_WORKFLOW_PATH = PROJECT_ROOT / ".github" / "workflows" / "weekly.yml"
RADAR_SERVICE_PATH = PROJECT_ROOT / "forward_radar_service.py"
RADAR_WORKFLOW_PATH = PROJECT_ROOT / ".github" / "workflows" / "forward_radar_monthly.yml"


class StandardsMonitorWorkflowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
        cls.weekly_workflow = WEEKLY_WORKFLOW_PATH.read_text(encoding="utf-8")
        cls.radar_service = RADAR_SERVICE_PATH.read_text(encoding="utf-8")
        cls.radar_workflow = RADAR_WORKFLOW_PATH.read_text(encoding="utf-8")

    def test_workflow_exists_with_expected_name_and_job(self):
        self.assertTrue(WORKFLOW_PATH.is_file())
        self.assertIn("name: 每月捷運機電規範更新監測", self.workflow)
        self.assertIn("jobs:\n  generate-standards-monthly:", self.workflow)
        self.assertNotIn("\t", self.workflow)
        self.assertNotRegex(self.workflow, r"^\s{1,1}\S", re.MULTILINE)

    def test_monthly_schedule_and_manual_dispatch(self):
        self.assertIn("cron: '37 1 2 * *'", self.workflow)
        self.assertIn("workflow_dispatch:", self.workflow)

    def test_runtime_runs_standalone_cli(self):
        self.assertIn("runs-on: ubuntu-latest", self.workflow)
        self.assertIn("actions/checkout@v4", self.workflow)
        self.assertIn("actions/setup-python@v5", self.workflow)
        self.assertIn("python-version: '3.11'", self.workflow)
        self.assertIn("pip install -r requirements.txt", self.workflow)
        self.assertIn(
            "python -u standards_monitor_main.py --output-dir output",
            self.workflow,
        )
        self.assertNotIn("python -u main.py", self.workflow)

    def test_artifact_upload_and_retention(self):
        self.assertIn("actions/upload-artifact@v4", self.workflow)
        self.assertIn("name: standards-monthly-${{ github.run_id }}", self.workflow)
        self.assertIn("output/standards_monthly_*.md", self.workflow)
        self.assertIn("output/standards_monthly_*.json", self.workflow)
        self.assertIn("retention-days: 90", self.workflow)

    def test_permissions_timeout_and_concurrency(self):
        self.assertIn("permissions:\n  contents: read", self.workflow)
        self.assertIn("timeout-minutes: 20", self.workflow)
        self.assertIn("group: standards-monthly", self.workflow)
        self.assertIn("cancel-in-progress: false", self.workflow)

    def test_no_report_secrets_or_email(self):
        for value in (
            "MAIAGENT_API_KEY", "MAIAGENT_CHATBOT_ID", "MAIAGENT_API_BASE",
            "GMAIL_USER", "GMAIL_APP_PASS", "RECIPIENTS", "SMTP", "MaiAgent",
        ):
            self.assertNotIn(value, self.workflow)

    def test_weekly_and_forward_radar_are_separate(self):
        self.assertIn("python -u main.py", self.weekly_workflow)
        self.assertNotIn("standards_monitor_main.py", self.weekly_workflow)
        self.assertIn("forward_radar_main.py", self.radar_workflow)
        self.assertNotIn("standards_monitor_main.py", self.radar_workflow)
        self.assertNotIn("standards_update", self.radar_service)


if __name__ == "__main__":
    unittest.main()
