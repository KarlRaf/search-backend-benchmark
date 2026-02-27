#!/usr/bin/env python3
"""
Search Backend Benchmark — CLI entry point.

Runs the Jira On-Prem Detector against one or more companies using
interchangeable search backends (Exa, Linkup), then writes a JSON + Markdown
report to results/.

Usage:
    # Full benchmark — all backends, CSV input
    python benchmark.py --input data/sample_companies.csv

    # Specific backends only
    python benchmark.py --input companies.csv --backends exa linkup

    # Single company quick test
    python benchmark.py --company "MongoDB" --domain "mongodb.com"

    # Choose model
    python benchmark.py --input companies.csv --model claude-haiku-4-5-20251001
"""

import argparse
import csv
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from backends.exa import ExaBackend
from backends.linkup import LinkupBackend
from eval.runner import run_company
from eval.reporter import generate_report

BACKEND_MAP = {
    "exa": ExaBackend,
    "linkup": LinkupBackend,
}

RESULTS_DIR = Path(__file__).parent / "results"


def load_companies_from_csv(csv_path: str) -> list[tuple[str, str]]:
    companies = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            company = row.get("company", "").strip()
            domain = row.get("domain", "").strip()
            if company and domain:
                companies.append((company, domain))
    return companies


def build_backends(backend_names: list[str]) -> list:
    backends = []
    errors = []
    for name in backend_names:
        cls = BACKEND_MAP.get(name)
        if cls is None:
            print(f"  [warn] unknown backend '{name}' — skipping")
            continue
        try:
            backends.append(cls())
        except ValueError as e:
            errors.append(f"  [error] {name}: {e}")
    if errors:
        for msg in errors:
            print(msg)
    return backends


def main():
    parser = argparse.ArgumentParser(
        description="Benchmark Exa vs Linkup as search backends for agentic Jira detection.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--input", metavar="CSV", help="CSV file with company,domain columns")
    source.add_argument("--company", metavar="NAME", help="Single company name (use with --domain)")

    parser.add_argument("--domain", metavar="DOMAIN", help="Domain for single-company mode")
    parser.add_argument(
        "--backends",
        nargs="+",
        default=["exa", "linkup"],
        choices=list(BACKEND_MAP.keys()),
        metavar="BACKEND",
        help="Backends to run (default: exa linkup)",
    )
    parser.add_argument(
        "--model",
        default="claude-sonnet-4-6",
        help="Anthropic model ID (default: claude-sonnet-4-6)",
    )
    parser.add_argument(
        "--output-dir",
        default=str(RESULTS_DIR),
        help="Directory to write results (default: results/)",
    )

    args = parser.parse_args()

    # Validate single-company mode
    if args.company and not args.domain:
        parser.error("--domain is required when using --company")

    # Load companies
    if args.input:
        if not os.path.exists(args.input):
            print(f"Error: CSV file not found: {args.input}", file=sys.stderr)
            sys.exit(1)
        companies = load_companies_from_csv(args.input)
        if not companies:
            print("Error: no valid rows found in CSV", file=sys.stderr)
            sys.exit(1)
    else:
        companies = [(args.company, args.domain)]

    # Build backends
    backends = build_backends(args.backends)
    if not backends:
        print("Error: no backends available — check your API keys in .env", file=sys.stderr)
        sys.exit(1)

    output_dir = Path(args.output_dir)

    print(f"\nSearch Backend Benchmark")
    print(f"  Companies : {len(companies)}")
    print(f"  Backends  : {', '.join(b.name for b in backends)}")
    print(f"  Model     : {args.model}")
    print(f"  Output    : {output_dir}/")
    print()

    all_results = []

    for company, domain in companies:
        for backend in backends:
            print(f"  [{backend.name}] {company} ({domain})...", end=" ", flush=True)
            t0 = time.monotonic()
            results = run_company(company, domain, [backend], model=args.model)
            elapsed = time.monotonic() - t0

            r = results[0]
            all_results.extend(results)

            if r.error:
                print(f"ERROR: {r.error}")
            else:
                print(
                    f"done ({elapsed:.0f}s, "
                    f"${r.total_cost_usd:.4f}, "
                    f"{r.classification}, "
                    f"conf={r.confidence_score})"
                )

    print()

    if not all_results:
        print("No results collected — exiting.")
        sys.exit(1)

    json_path, md_path = generate_report(all_results, output_dir, model=args.model)

    print(f"Report written to:")
    print(f"  {json_path}")
    print(f"  {md_path}")
    print()


if __name__ == "__main__":
    main()
