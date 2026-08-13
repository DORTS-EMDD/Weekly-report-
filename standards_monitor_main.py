"""CLI entry point for the standalone monthly metro standards monitor."""

from __future__ import annotations

import argparse
import datetime

from standards_monitor_service import run_standards_monitor, write_standards_outputs


def _parse_date(value: str) -> datetime.date:
    try:
        return datetime.date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("日期必須使用 YYYY-MM-DD") from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="產生捷運機電規範更新月報")
    parser.add_argument("--as-of-date", type=_parse_date, default=None)
    parser.add_argument("--start-date", type=_parse_date, default=None)
    parser.add_argument("--end-date", type=_parse_date, default=None)
    parser.add_argument("--output-dir", default="output")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = run_standards_monitor(
        as_of_date=args.as_of_date,
        start_date=args.start_date,
        end_date=args.end_date,
    )
    paths = write_standards_outputs(result, args.output_dir)
    print(f"監測期間：{result['period']['start_date']} ～ {result['period']['end_date']}")
    print(f"符合更新：{result['eligible_count']}，排除：{result['rejected_count']}")
    print(f"Markdown：{paths['markdown']}")
    print(f"JSON：{paths['json']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
