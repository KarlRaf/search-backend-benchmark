# Search Backend Benchmark — Exa vs Linkup

A benchmark that runs the same agentic research loop against two interchangeable search backends — [Exa](https://exa.ai) and [Linkup](https://www.linkup.so) — and compares result quality, cost, search efficiency, and latency side-by-side on the same set of companies.

The research task: detect whether a company uses Jira on-premises (Data Center/Server) vs Jira Cloud. This is a non-trivial agentic task that requires 10–15 web searches, subdomain resolution, and multi-step reasoning — a real-world stress test for search APIs, not a keyword query benchmark.

## Background

In April 2026, Atlassian ends support for all Data Center products. Thousands of companies still running self-hosted Jira face a decision: migrate to Jira Cloud, or switch tools entirely. Identifying which companies are on-prem — and how far along they are in the migration decision — is a high-value signal for tools like Linear that are actively displacing Jira.

This benchmark was built to evaluate whether Exa and Linkup are interchangeable search backends for agentic research loops of this kind. The output is a side-by-side comparison, not a winner declaration — quality is judged manually.

## Quick Start

```bash
git clone https://github.com/your-org/search-backend-benchmark
cd search-backend-benchmark

pip install -r requirements.txt

cp .env.example .env
# Add your keys to .env

# Quick test — single company, Exa only
python benchmark.py --company "MongoDB" --domain "mongodb.com" --backends exa

# Full benchmark — all backends, sample CSV
python benchmark.py --input data/sample_companies.csv

# Specific backends
python benchmark.py --input data/sample_companies.csv --backends exa linkup
```

Results are written to `results/YYYY-MM-DD-HHMMSS/`:
- `raw_results.json` — full structured data, machine-readable
- `report.md` — aggregate summary + per-company side-by-side tables

## CSV Format

```csv
company,domain,expected_classification
MongoDB,mongodb.com,ON_PREM_STABLE
Stripe,stripe.com,CLOUD
```

The `expected_classification` column is optional — it is not used by the benchmark but helps you track ground truth when reviewing results.

## Adding a New Backend

Implement the `SearchBackend` abstract class (~20 lines):

```python
# backends/mybackend.py
import os
from .base import SearchBackend

class MyBackend(SearchBackend):
    name = "mybackend"

    def __init__(self):
        self._api_key = os.environ["MY_API_KEY"]

    def search(self, query: str, num_results: int = 5) -> tuple[list[dict], float]:
        # Call your API here
        results = [{"url": ..., "title": ..., "snippet": ...}]
        cost_usd = 0.0  # or actual cost if your API exposes it
        return results, cost_usd
```

Then register it in `benchmark.py`:

```python
from backends.mybackend import MyBackend
BACKEND_MAP = {"exa": ExaBackend, "linkup": LinkupBackend, "mybackend": MyBackend}
```

## Metrics Explained

| Metric | Description |
|--------|-------------|
| Classification | ON_PREM_STABLE / ON_PREM_PLANNING / ON_PREM_MIGRATING / CLOUD / HYBRID / NO_JIRA / INCONCLUSIVE |
| Confidence | 0–100 score computed by the agent from evidence strength |
| Search calls | Number of web_search tool calls made |
| Search cost | API cost charged by the search backend (USD) |
| Anthropic cost | Claude API cost for input + output tokens (USD) |
| Total cost | Search cost + Anthropic cost |
| Latency | Wall-clock time for the full agentic loop |
| Primary evidence | One-line strongest signal found by the agent |

## Classification Codes

| Code | Meaning |
|------|---------|
| ON_PREM_STABLE | On-prem confirmed, no migration signals |
| ON_PREM_PLANNING | On-prem + early signals (RFPs, DC EOL mentions, evaluations) |
| ON_PREM_MIGRATING | On-prem + active migration in progress |
| CLOUD | Atlassian.net only, no on-prem signals |
| HYBRID | Both on-prem and cloud, no clear direction |
| NO_JIRA | No Jira evidence found |
| INCONCLUSIVE | Weak signals only, confidence below threshold |

## Known Limitations

- **No ground truth validation.** Results are shown side-by-side and judged manually. The `expected_classification` column in the CSV is for your reference only.
- **Anthropic rate limits.** Backends run sequentially per company to avoid conflicts. Large CSVs will take time. The agent retries automatically with exponential backoff.
- **Linkup cost tracking.** The linkup-sdk does not expose per-request cost in the response object. Search cost for Linkup is recorded as $0.0000 in reports. See [Linkup pricing](https://www.linkup.so/pricing) for current rates.
- **Search query semantics.** The agent uses `site:` operators and exact-match strings. Some search backends handle these differently, which affects recall. This is intentional — it is part of what the benchmark measures.

## Requirements

- Python 3.10+
- `ANTHROPIC_API_KEY` — [console.anthropic.com](https://console.anthropic.com)
- `EXA_API_KEY` — [exa.ai](https://exa.ai) (only needed for Exa backend)
- `LINKUP_API_KEY` — [linkup.so](https://www.linkup.so) (only needed for Linkup backend)

## License

MIT
