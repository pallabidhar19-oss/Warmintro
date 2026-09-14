#!/usr/bin/env python3
"""CLI entry point for WarmIntro.

Usage:
    python run_demo.py --input data/sample_leads.csv --output output/

Requires ANTHROPIC_API_KEY to be set (see .env.example).
"""

import argparse
from pathlib import Path

from warmintro.pipeline import run_pipeline


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the WarmIntro outreach pipeline over a lead CSV.")
    parser.add_argument("--input", type=Path, default=Path("data/sample_leads.csv"), help="Path to input lead CSV (columns: name,title,company,notes)")
    parser.add_argument("--output", type=Path, default=Path("output"), help="Directory to write drafts.md and drafts.csv to")
    args = parser.parse_args()

    results = run_pipeline(args.input, args.output)

    passed = sum(1 for r in results if r.qa_verdict == "PASS")
    print(f"\nDone. {passed}/{len(results)} leads passed QA.")
    print(f"Report written to {args.output / 'drafts.md'} and {args.output / 'drafts.csv'}")


if __name__ == "__main__":
    main()
