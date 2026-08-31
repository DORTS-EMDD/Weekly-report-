"""Focused regressions for the weekly GitHub Actions schedule."""

import re
import unittest
from pathlib import Path


WORKFLOW_PATH = Path(__file__).resolve().parent / ".github" / "workflows" / "weekly.yml"


class WeeklyScheduleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = WORKFLOW_PATH.read_text(encoding="utf-8")

    def test_weekly_schedule_runs_once_each_monday_at_0037_utc(self):
        match = re.search(r"^\s*- cron:\s*'([^']+)'", self.workflow, re.MULTILINE)
        self.assertIsNotNone(match)
        fields = match.group(1).split()
        self.assertEqual(fields, ["37", "0", "*", "*", "1"])

    def test_weekly_schedule_is_not_daily_or_application_gated(self):
        self.assertNotIn("cron: '37 0 * * *'", self.workflow)
        self.assertNotIn("weekday", self.workflow.casefold())
        self.assertNotIn("datetime", self.workflow.casefold())
        self.assertIn("python -u main.py", self.workflow)


if __name__ == "__main__":
    unittest.main()
