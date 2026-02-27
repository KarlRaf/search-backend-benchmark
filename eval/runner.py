"""
Eval runner — CompanyResult dataclass and run_company().

Runs each backend sequentially (not parallel) to avoid Anthropic rate limit
conflicts. Errors are captured per-result rather than crashing the full run.
"""

import time
from dataclasses import dataclass, field
from typing import Optional

from backends.base import SearchBackend
from agent.detector import JiraOnPremDetector
from agent.costs import RunCosts


@dataclass
class CompanyResult:
    """All metrics captured for one company × backend run."""

    # Identity
    company: str
    domain: str
    backend: str  # backend.name

    # Classification
    classification: str = ""
    confidence_score: Optional[int] = None
    primary_evidence: str = ""

    # Usage
    search_calls: int = 0
    tool_calls_total: int = 0
    anthropic_input_tokens: int = 0
    anthropic_output_tokens: int = 0

    # Cost
    anthropic_cost_usd: float = 0.0
    search_cost_usd: float = 0.0
    total_cost_usd: float = 0.0

    # Performance
    latency_seconds: float = 0.0

    # Raw output
    raw_output: str = ""

    # Error (None = success)
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "company": self.company,
            "domain": self.domain,
            "backend": self.backend,
            "classification": self.classification,
            "confidence_score": self.confidence_score,
            "primary_evidence": self.primary_evidence,
            "search_calls": self.search_calls,
            "tool_calls_total": self.tool_calls_total,
            "anthropic_input_tokens": self.anthropic_input_tokens,
            "anthropic_output_tokens": self.anthropic_output_tokens,
            "anthropic_cost_usd": round(self.anthropic_cost_usd, 6),
            "search_cost_usd": round(self.search_cost_usd, 6),
            "total_cost_usd": round(self.total_cost_usd, 6),
            "latency_seconds": round(self.latency_seconds, 2),
            "raw_output": self.raw_output,
            "error": self.error,
        }


def _parse_field(raw_output: str, field_name: str) -> str:
    """Extract a single field value from the structured output block."""
    for line in raw_output.splitlines():
        if line.startswith(f"{field_name}:"):
            return line[len(f"{field_name}:"):].strip()
    return ""


def _run_single(
    company: str,
    domain: str,
    backend: SearchBackend,
    model: str,
) -> CompanyResult:
    """Run one company × backend pair and return a populated CompanyResult."""
    result = CompanyResult(company=company, domain=domain, backend=backend.name)

    t0 = time.monotonic()
    try:
        detector = JiraOnPremDetector(search_backend=backend, model=model)
        raw_output, costs = detector.research(company, domain)

        result.latency_seconds = time.monotonic() - t0
        result.raw_output = raw_output

        # Parse structured fields from output
        result.classification = _parse_field(raw_output, "classification")
        confidence_str = _parse_field(raw_output, "confidence_score")
        try:
            result.confidence_score = int(confidence_str)
        except (ValueError, TypeError):
            result.confidence_score = None
        result.primary_evidence = _parse_field(raw_output, "primary_evidence")

        # Populate cost/usage from RunCosts
        result.search_calls = costs.search_calls
        result.tool_calls_total = costs.api_calls  # Anthropic API calls
        result.anthropic_input_tokens = costs.input_tokens
        result.anthropic_output_tokens = costs.output_tokens
        result.anthropic_cost_usd = costs.anthropic_cost_usd
        result.search_cost_usd = costs.search_cost_usd
        result.total_cost_usd = costs.total_cost_usd

    except Exception as exc:
        result.latency_seconds = time.monotonic() - t0
        result.error = str(exc)

    return result


def run_company(
    company: str,
    domain: str,
    backends: list[SearchBackend],
    model: str = "claude-sonnet-4-6",
) -> list[CompanyResult]:
    """
    Run all backends for a single company, sequentially.

    Sequential execution avoids Anthropic rate limit conflicts when running
    multiple agentic loops back-to-back.

    Returns one CompanyResult per backend.
    """
    results = []
    for backend in backends:
        result = _run_single(company, domain, backend, model)
        results.append(result)
    return results
