"""GitHub Actions entry point for the shared report workflow."""

import datetime
import os
import sys
from pathlib import Path

from config import ADVANCED_REGIONS, DEFAULT_SELECTED_TYPES
from email_service import send_email
from maiagent_service import call_maiagent_cloud
from report_workflow_service import (
    WorkflowDependencies,
    build_automation_run_config,
    run_report_workflow,
)
from semantic_validation_service import SemanticSupportJudge


def _required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"未設定必要環境變數：{name}")
    return value


def _lookback_days() -> int:
    try:
        value = int(os.environ.get("NEWS_LOOKBACK_DAYS", "7"))
    except ValueError:
        value = 7
    return value if value in {7, 30} else 7


def _save_report(report_md: str, report_date: datetime.date) -> Path:
    reports_dir = Path("reports")
    reports_dir.mkdir(parents=True, exist_ok=True)
    dated_path = reports_dir / f"report_{report_date:%Y%m%d}.md"
    dated_path.write_text(report_md, encoding="utf-8")
    (reports_dir / "latest.md").write_text(report_md, encoding="utf-8")
    return dated_path


def main() -> int:
    try:
        import feedparser
        from ddgs import DDGS
    except ModuleNotFoundError as exc:
        raise RuntimeError(f"自動報告依賴未安裝：{exc.name}") from exc

    today = datetime.date.today()
    lookback_days = _lookback_days()
    selected_types = list(DEFAULT_SELECTED_TYPES)
    config, _ = build_automation_run_config(
        today=today,
        lookback_days=lookback_days,
        selected_types=selected_types,
        active_regions=list(ADVANCED_REGIONS),
    )
    api_key = _required_env("MAIAGENT_API_KEY")
    chatbot_id = _required_env("MAIAGENT_CHATBOT_ID")
    api_base = os.environ.get("MAIAGENT_API_BASE", "https://api.maiagent.ai")

    def call_report_agent(prompt: str) -> str:
        return call_maiagent_cloud(
            prompt,
            api_key=api_key,
            chatbot_id=chatbot_id,
            api_base=api_base,
        )

    semantic_judge = SemanticSupportJudge(call_report_agent)

    print("=" * 55)
    print("  國際捷運技術週報 自動產生器")
    print(f"  日期：{today:%Y年%m月%d日}")
    print(f"  期間：{config.date_range}")
    print(f"  搜尋天數：{lookback_days} 天")
    print("  Pipeline：shared report_workflow_service")
    print("=" * 55)

    result = run_report_workflow(
        config=config,
        dependencies=WorkflowDependencies(
            ddgs_client_factory=DDGS,
            feedparser_module=feedparser,
            call_maiagent=call_report_agent,
            call_semantic_judge=semantic_judge.validate,
            status_callback=lambda message: print(f"[INFO] {message}"),
        ),
    )
    dated_path = _save_report(result.report_md, today)
    print(f"[INFO] 已儲存：{dated_path}")

    sender = _required_env("GMAIL_USER")
    password = _required_env("GMAIL_APP_PASS")
    recipients = [
        item.strip()
        for item in _required_env("RECIPIENTS").split(",")
        if item.strip()
    ]
    if not recipients:
        raise RuntimeError("RECIPIENTS 未包含有效收件信箱")
    sent = send_email(
        result.report_md,
        recipients,
        subject=config.report_title,
        sender=sender,
        password=password,
        pdf_filename=f"metro_report_{today:%Y%m%d}.pdf",
    )
    if not sent:
        raise RuntimeError("Email 寄送失敗")
    print(
        f"[INFO] 完成：候選 {len(result.model_candidates)} 筆，"
        f"入選 {len(result.selected_candidates)} 筆，搜尋 {result.search_count} 組"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        raise
