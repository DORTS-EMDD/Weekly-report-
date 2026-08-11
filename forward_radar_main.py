"""CLI entry point for the standalone monthly forward technology radar."""

import argparse

from forward_radar_service import (
    DEFAULT_LOOKBACK_DAYS,
    run_forward_radar,
    write_forward_radar_outputs,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the monthly forward technology radar")
    parser.add_argument("--lookback-days", type=int, default=DEFAULT_LOOKBACK_DAYS)
    parser.add_argument("--output-dir", default="output")
    args = parser.parse_args(argv)

    from ddgs import DDGS

    result = run_forward_radar(
        lookback_days=args.lookback_days,
        ddgs_client_factory=DDGS,
    )
    paths = write_forward_radar_outputs(result, args.output_dir)
    counts = result["counts"]
    print(
        "Forward Radar complete: "
        f"eligible={counts['report_eligible']} "
        f"watchlist={counts['radar_watchlist']} "
        f"rejected={counts['rejected']}"
    )
    print(f"Markdown: {paths['markdown']}")
    print(f"JSON: {paths['json']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
