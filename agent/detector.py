"""
Jira On-Prem Detector — backend-agnostic agentic research loop.

Ported from TRA monorepo infrastructure/agents/jira-onprem-detector/agent.py.
The only structural change: takes a SearchBackend at init instead of importing
Exa directly, making the agent fully backend-agnostic.
"""

import os
import time
import json
import requests
import anthropic

from .costs import RunCosts
from .prompts import SYSTEM_PROMPT
from backends.base import SearchBackend

MODEL = "claude-sonnet-4-6"
MAX_TOOL_CALLS = 15

TOOL_DEFINITIONS = [
    {
        "name": "web_search",
        "description": (
            "Search the web. Use this for site: queries, exact-match "
            "searches, and all research steps. Your query is passed verbatim — "
            "write precise queries."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The exact search query to run.",
                },
                "num_results": {
                    "type": "integer",
                    "description": "Number of results to return (default 5, max 10).",
                    "default": 5,
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "check_subdomain",
        "description": (
            "Send an HTTP HEAD request to https://{subdomain} and follow redirects. "
            "Use this to check whether jira.{domain}, issues.{domain}, "
            "tickets.{domain}, etc. resolve to a live server. "
            "If final_url contains atlassian.net it is Jira Cloud, not on-prem."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "subdomain": {
                    "type": "string",
                    "description": (
                        "The full subdomain to check, e.g. 'jira.siemens.com' or "
                        "'issues.stripe.com'. Do not include https://."
                    ),
                },
            },
            "required": ["subdomain"],
        },
    },
]


def _check_subdomain(subdomain: str) -> dict:
    """HTTP HEAD request to detect live subdomains."""
    url = f"https://{subdomain}" if not subdomain.startswith("http") else subdomain
    try:
        resp = requests.head(url, timeout=5, allow_redirects=True)
        return {
            "exists": True,
            "status_code": resp.status_code,
            "final_url": resp.url,
        }
    except Exception:
        return {"exists": False}


class JiraOnPremDetector:
    """
    Agentic Jira on-prem detector that works with any SearchBackend.

    Usage:
        from backends import ExaBackend
        from agent import JiraOnPremDetector

        detector = JiraOnPremDetector(search_backend=ExaBackend())
        output, costs = detector.research("MongoDB", "mongodb.com")
    """

    def __init__(self, search_backend: SearchBackend, model: str = MODEL):
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable not set")
        self.client = anthropic.Anthropic(api_key=api_key)
        self.search_backend = search_backend
        self.model = model

    def _dispatch_tool(self, tool_name: str, tool_input: dict, costs: RunCosts):
        """Execute the named tool, update costs, return a JSON-serializable result."""
        if tool_name == "web_search":
            results, search_cost = self.search_backend.search(
                query=tool_input["query"],
                num_results=tool_input.get("num_results", 5),
            )
            costs.search_cost_usd += search_cost
            costs.search_calls += 1
            return results
        elif tool_name == "check_subdomain":
            return _check_subdomain(subdomain=tool_input["subdomain"])
        else:
            return {"error": f"Unknown tool: {tool_name}"}

    def _create_with_retry(
        self, messages: list, max_retries: int = 5
    ) -> anthropic.types.Message:
        """Call the API with exponential backoff on rate limit errors."""
        delay = 60
        for attempt in range(max_retries):
            try:
                return self.client.messages.create(
                    model=self.model,
                    max_tokens=4096,
                    system=SYSTEM_PROMPT,
                    tools=TOOL_DEFINITIONS,
                    messages=messages,
                )
            except anthropic.RateLimitError:
                if attempt == max_retries - 1:
                    raise
                print(
                    f"  [rate limit] waiting {delay}s before retry "
                    f"{attempt + 2}/{max_retries}..."
                )
                time.sleep(delay)
                delay = min(delay * 2, 300)

    def research(self, company_name: str, domain: str) -> tuple[str, RunCosts]:
        """
        Run the agentic research loop for a single company.

        Returns (output_text, costs) where output_text is the structured result
        and costs contains token and dollar breakdowns for Anthropic + search backend.
        """
        messages = [
            {
                "role": "user",
                "content": (
                    f"Research whether {company_name} ({domain}) uses Jira on-premises "
                    f"or Jira Cloud. Follow all 6 research steps and return the output "
                    f"in the exact structured format specified."
                ),
            }
        ]

        costs = RunCosts()
        tool_call_count = 0

        while True:
            response = self._create_with_retry(messages)

            costs.api_calls += 1
            costs.input_tokens += response.usage.input_tokens
            costs.output_tokens += response.usage.output_tokens

            text_blocks = [b for b in response.content if b.type == "text"]
            tool_blocks = [b for b in response.content if b.type == "tool_use"]

            if response.stop_reason == "end_turn":
                output = text_blocks[-1].text.strip() if text_blocks else ""
                if "classification:" not in output:
                    messages.append({"role": "assistant", "content": response.content})
                    messages.append({
                        "role": "user",
                        "content": (
                            "You have enough data. Produce the final structured output now — "
                            "starting with 'classification:'. No other text."
                        ),
                    })
                    nudge_response = self._create_with_retry(messages)
                    costs.api_calls += 1
                    costs.input_tokens += nudge_response.usage.input_tokens
                    costs.output_tokens += nudge_response.usage.output_tokens
                    nudge_text = [b for b in nudge_response.content if b.type == "text"]
                    output = nudge_text[-1].text.strip() if nudge_text else "(no output)"
                return output, costs

            if response.stop_reason == "tool_use":
                if tool_call_count >= MAX_TOOL_CALLS:
                    output = text_blocks[-1].text.strip() if text_blocks else "(max tool calls reached)"
                    return output, costs

                messages.append({"role": "assistant", "content": response.content})

                tool_results = []
                for block in tool_blocks:
                    tool_call_count += 1
                    result = self._dispatch_tool(block.name, block.input, costs)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(result),
                    })

                messages.append({"role": "user", "content": tool_results})
                continue

            output = (
                text_blocks[-1].text.strip()
                if text_blocks
                else f"(unexpected stop_reason: {response.stop_reason})"
            )
            return output, costs
