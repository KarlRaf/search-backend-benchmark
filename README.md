# Search Backend Benchmark — Exa vs Linkup

A benchmark that runs the same agentic research loop against two interchangeable search backends — [Exa](https://exa.ai) and [Linkup](https://www.linkup.so) — and compares result quality, cost, search efficiency, and latency side-by-side on the same set of companies.

The research task: classify how deeply a company has integrated AI/LLM into its products. This requires synthesizing signals across product pages, GitHub repositories, job postings, engineering blogs, and tech stack databases — a non-trivial agentic task that cannot be answered by a single source lookup. That makes it a real-world stress test for search APIs, not a keyword query benchmark.

## Why This Task

"Is this company AI-native, or just using the word AI?" is one of the most common and genuinely hard research questions in sales, investing, and competitive analysis right now. The answer is rarely on one page. The agent has to:

- Find the company's GitHub org and check for AI/ML repos and dependencies
- Distinguish named, shipped AI features from marketing language
- Cross-reference job posts to assess how seriously they're investing in AI engineering
- Synthesize conflicting signals (e.g. a company that says "AI-powered" everywhere but has no ML engineers)

This is exactly the kind of task where search backend quality matters — and where Exa and Linkup will diverge.

## Quick Start

```bash
git clone https://github.com/KarlRaf/search-backend-benchmark
cd search-backend-benchmark

pip install -r requirements.txt

cp .env.example .env
# Add your keys to .env

# Quick test — single company, Exa only
python benchmark.py --company "Cursor" --domain "cursor.sh" --backends exa

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
Cursor,cursor.sh,AI_NATIVE
Figma,figma.com,AI_AUGMENTED
```

The `expected_classification` column is optional — it is not used by the benchmark but helps you track ground truth when reviewing results.

## Classification Codes

| Code | Meaning | Example |
|------|---------|---------|
| `AI_NATIVE` | AI is the core product. Remove it and there is no product. | Cursor, Perplexity |
| `AI_INTEGRATED` | AI is a primary differentiator, deeply embedded in the core experience. | GitHub Copilot, Glean |
| `AI_AUGMENTED` | Traditional product with substantial, named AI features shipped. | Figma, Notion |
| `AI_ADJACENT` | AI mentioned but only in auxiliary or support capacity. No user-facing AI features. | Stripe |
| `EXPLORING` | Job posts or roadmap signals suggest AI is coming. No shipped features confirmed. | — |
| `NO_AI_SIGNALS` | No evidence of AI in product, strategy, or hiring. | Basecamp |

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
| Classification | AI_NATIVE / AI_INTEGRATED / AI_AUGMENTED / AI_ADJACENT / EXPLORING / NO_AI_SIGNALS |
| Confidence | 0–100 score computed by the agent from evidence strength |
| Search calls | Number of web_search tool calls made |
| Search cost | API cost charged by the search backend (USD) |
| Anthropic cost | Claude API cost for input + output tokens (USD) |
| Total cost | Search cost + Anthropic cost |
| Latency | Wall-clock time for the full agentic loop |
| Primary evidence | One-line strongest signal found by the agent |

## Research Steps

The agent follows a fixed 6-step methodology per company:

1. **Product page** — check for a dedicated AI subdomain, search the company's own site for AI features
2. **GitHub org** — look for AI/ML repos, check for AI model dependencies (`openai`, `anthropic`, `langchain`, `huggingface`)
3. **Job posts** — distinguish AI product engineering roles from internal AI tooling roles
4. **Engineering blog** — look for AI feature launch announcements and technical deep-dives
5. **Tech stack** — check Stackshare, declared integrations, AI provider partnerships
6. **Company context** — founding year, employee count, industry (incumbents vs AI-native startups)

## Known Limitations

- **No ground truth validation.** Results are shown side-by-side and judged manually. The `expected_classification` column in the CSV is for your reference only.
- **Anthropic rate limits.** Backends run sequentially per company to avoid conflicts. Large CSVs will take time. The agent retries automatically with exponential backoff.
- **Linkup cost tracking.** The linkup-sdk does not expose per-request cost in the response object. Search cost for Linkup is recorded as $0.0000 in reports. See [Linkup pricing](https://www.linkup.so/pricing) for current rates.
- **Fast-moving signals.** AI adoption changes rapidly. Results reflect the state of the web at the time of the run.

## Requirements

- Python 3.10+
- `ANTHROPIC_API_KEY` — [console.anthropic.com](https://console.anthropic.com)
- `EXA_API_KEY` — [exa.ai](https://exa.ai) (only needed for Exa backend)
- `LINKUP_API_KEY` — [linkup.so](https://www.linkup.so) (only needed for Linkup backend)

## License

MIT
