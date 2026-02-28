"""
Report generation — JSON (raw) + Markdown (human-readable).

Writes to results/YYYY-MM-DD-HHMMSS/ and returns both file paths.
"""

import json
from datetime import datetime
from pathlib import Path
from collections import defaultdict
from typing import Optional

from .runner import CompanyResult


def _fmt_cost(value: Optional[float]) -> str:
    if value is None:
        return "N/A"
    return f"${value:.4f}"


def _fmt_latency(value: float) -> str:
    return f"{value:.0f}s"


def _avg(values: list) -> Optional[float]:
    valid = [v for v in values if v is not None]
    return sum(valid) / len(valid) if valid else None


def _generate_markdown(
    results: list[CompanyResult],
    run_ts: str,
    model: str,
) -> str:
    # Collect backend names in stable order
    backend_names = list(dict.fromkeys(r.backend for r in results))
    companies = list(dict.fromkeys((r.company, r.domain) for r in results))

    # Index results: (company, domain, backend) -> CompanyResult
    index: dict[tuple, CompanyResult] = {}
    for r in results:
        index[(r.company, r.domain, r.backend)] = r

    lines = []

    # Header
    lines.append("# Search Backend Benchmark — AI Adoption Detection")
    lines.append("")
    lines.append(
        f"Run: {run_ts} | "
        f"Companies: {len(companies)} | "
        f"Backends: {', '.join(backend_names)} | "
        f"Model: {model}"
    )
    lines.append("")

    # Aggregate summary
    lines.append("## Aggregate Summary")
    lines.append("")

    header = "| Metric              | " + " | ".join(f"{b:<6}" for b in backend_names) + " |"
    sep = "|---------------------|" + "|".join("-" * 8 for _ in backend_names) + "|"
    lines.append(header)
    lines.append(sep)

    def agg_row(label: str, extractor):
        per_backend = {}
        for b in backend_names:
            vals = [
                extractor(index[(c, d, b)])
                for (c, d) in companies
                if (c, d, b) in index and index[(c, d, b)].error is None
            ]
            per_backend[b] = _avg(vals)
        cells = " | ".join(
            (f"${per_backend[b]:.4f}" if per_backend[b] is not None and label.endswith("cost") else
             f"{per_backend[b]:.1f}" if per_backend[b] is not None else "N/A")
            for b in backend_names
        )
        return f"| {label:<19} | {cells} |"

    def agg_cost_row(label: str, extractor):
        per_backend = {}
        for b in backend_names:
            vals = [
                extractor(index[(c, d, b)])
                for (c, d) in companies
                if (c, d, b) in index and index[(c, d, b)].error is None
            ]
            per_backend[b] = _avg(vals)
        cells = " | ".join(
            f"${per_backend[b]:.4f}" if per_backend[b] is not None else "N/A"
            for b in backend_names
        )
        return f"| {label:<19} | {cells} |"

    def agg_plain_row(label: str, extractor, fmt=".1f"):
        per_backend = {}
        for b in backend_names:
            vals = [
                extractor(index[(c, d, b)])
                for (c, d) in companies
                if (c, d, b) in index and index[(c, d, b)].error is None
            ]
            per_backend[b] = _avg(vals)
        cells = " | ".join(
            format(per_backend[b], fmt) if per_backend[b] is not None else "N/A"
            for b in backend_names
        )
        return f"| {label:<19} | {cells} |"

    lines.append(agg_cost_row("Avg search cost", lambda r: r.search_cost_usd))
    lines.append(agg_cost_row("Avg Anthropic cost", lambda r: r.anthropic_cost_usd))
    lines.append(agg_cost_row("Avg total cost", lambda r: r.total_cost_usd))
    lines.append(agg_plain_row("Avg search calls", lambda r: r.search_calls, ".1f"))
    lines.append(agg_plain_row("Avg latency (s)", lambda r: r.latency_seconds, ".0f"))
    lines.append(agg_plain_row("Avg confidence", lambda r: r.confidence_score if r.confidence_score is not None else 0, ".0f"))

    # Agreements
    if len(backend_names) >= 2:
        agreements = 0
        comparable = 0
        for (c, d) in companies:
            classifications = [
                index[(c, d, b)].classification
                for b in backend_names
                if (c, d, b) in index and index[(c, d, b)].error is None
            ]
            if len(classifications) >= 2:
                comparable += 1
                if len(set(classifications)) == 1:
                    agreements += 1
        lines.append(f"| {'Agreements':<19} | {agreements}/{comparable} companies classified the same |")

    # Linkup cost note
    if "linkup" in backend_names:
        lines.append("")
        lines.append(
            "> **Note:** Linkup search cost shown as $0.0000 — the linkup-sdk does not "
            "expose per-request cost in the response object. Check "
            "[Linkup pricing](https://www.linkup.so/pricing) for current rates."
        )

    lines.append("")

    # Per-company tables
    lines.append("## Results by Company")
    lines.append("")

    field_labels = [
        ("Classification", lambda r: r.classification or "(none)"),
        ("Confidence", lambda r: str(r.confidence_score) if r.confidence_score is not None else "N/A"),
        ("Search calls", lambda r: str(r.search_calls)),
        ("Search cost", lambda r: f"${r.search_cost_usd:.4f}"),
        ("Anthropic cost", lambda r: f"${r.anthropic_cost_usd:.4f}"),
        ("Total cost", lambda r: f"${r.total_cost_usd:.4f}"),
        ("Latency", lambda r: _fmt_latency(r.latency_seconds)),
        ("Primary evidence", lambda r: r.primary_evidence or "(none)"),
        ("Error", lambda r: r.error or ""),
    ]

    for (company, domain) in companies:
        lines.append(f"### {company} ({domain})")
        lines.append("")

        col_header = "| Field              | " + " | ".join(f"{b:<28}" for b in backend_names) + " |"
        col_sep = "|--------------------|" + "|".join("-" * 30 for _ in backend_names) + "|"
        lines.append(col_header)
        lines.append(col_sep)

        for label, extractor in field_labels:
            cells = []
            for b in backend_names:
                key = (company, domain, b)
                if key in index:
                    r = index[key]
                    if r.error and label not in ("Error", "Latency"):
                        cells.append("ERROR")
                    else:
                        cells.append(extractor(r))
                else:
                    cells.append("—")
            row = "| {:<18} | {} |".format(
                label,
                " | ".join(f"{c:<28}" for c in cells),
            )
            lines.append(row)

        lines.append("")

    return "\n".join(lines)


def generate_report(
    results: list[CompanyResult],
    output_dir: Path,
    model: str = "claude-sonnet-4-6",
) -> tuple[Path, Path]:
    """
    Write raw_results.json and report.md to output_dir/YYYY-MM-DD-HHMMSS/.

    Returns (json_path, markdown_path).
    """
    run_ts = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    run_dir = output_dir / run_ts
    run_dir.mkdir(parents=True, exist_ok=True)

    # JSON output
    json_path = run_dir / "raw_results.json"
    json_path.write_text(
        json.dumps([r.to_dict() for r in results], indent=2),
        encoding="utf-8",
    )

    # Markdown report
    display_ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    md_content = _generate_markdown(results, display_ts, model)
    md_path = run_dir / "report.md"
    md_path.write_text(md_content, encoding="utf-8")

    return json_path, md_path
