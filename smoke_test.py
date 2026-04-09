#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path

import speedia


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a real smoke test for speedia")
    parser.add_argument("sub_url", help="Real subscription URL or content")
    parser.add_argument("--limit", type=int, default=1, help="How many proxies to test during smoke test")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report_dir = speedia.get_report_dir()
    report_dir.mkdir(parents=True, exist_ok=True)
    json_path = report_dir / "speed_results.json"
    html_path = report_dir / "speed_results.html"
    json_path.unlink(missing_ok=True)
    html_path.unlink(missing_ok=True)

    original_argv = sys.argv[:]
    original_open_report = speedia.open_report
    try:
        sys.argv = ["speedia.py", "--limit", str(args.limit), args.sub_url]
        speedia.open_report = lambda path: (False, "")
        speedia.main()
    finally:
        sys.argv = original_argv
        speedia.open_report = original_open_report

    if not json_path.exists():
        raise SystemExit(f"Smoke test failed: missing {json_path}")
    if not html_path.exists():
        raise SystemExit(f"Smoke test failed: missing {html_path}")

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    tested_count = payload.get("tested_count", 0)
    results = payload.get("results", [])
    if tested_count <= 0 or not results:
        raise SystemExit("Smoke test failed: no test results produced")

    print(f"[done] Smoke test passed: tested_count={tested_count}, results={len(results)}")
    print(f"[done] JSON: {json_path}")
    print(f"[done] HTML: {html_path}")


if __name__ == "__main__":
    main()
