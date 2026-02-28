"""
Company Research Agent — backend-agnostic agentic research loop.

A general-purpose research agent that uses Claude + a pluggable search backend
to answer structured questions about companies and return a classified,
scored output.
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
MAX_TOOL_CALLS = 10

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
                    "description": "Number of results to return (default 3, max 5).",
                    "default": 3,
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


class CompanyResearchAgent:
    """
    Agentic company research agent that works with any SearchBackend.

    Usage:
        from backends import ExaBackend
        from agent import CompanyResearchAgent

        agent = CompanyResearchAgent(search_backend=ExaBackend())
        output, costs = agent.research("Cursor", "cursor.sh")
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
        self, messages: list, max_retries: int = 5, tools: bool = True
    ) -> anthropic.types.Message:
        """Call the API with exponential backoff on rate limit errors.

        Pass tools=False to make a text-only call (used for forced output and
        nudges — prevents Claude from calling more tools when we need final output).
        """
        delay = 60
        kwargs = dict(
            model=self.model,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            messages=messages,
        )
        if tools:
            kwargs["tools"] = TOOL_DEFINITIONS
        for attempt in range(max_retries):
            try:
                return self.client.messages.create(**kwargs)
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
                    f"Research how deeply {company_name} ({domain}) has integrated AI/LLM "
                    f"into its products. Follow all 6 research steps and return the output "
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
                # Nudge up to 2 times if structured output is missing.
                # Each iteration appends the previous response then a nudge user message.
                # If Claude responds with tool_use instead of text, stop nudging —
                # we cannot append tool_use without tool_results.
                for _ in range(2):
                    if "classification:" in output:
                        break
                    messages.append({"role": "assistant", "content": response.content})
                    messages.append({
                        "role": "user",
                        "content": (
                            "You have enough data. Produce the final structured output now — "
                            "starting with 'classification:'. No other text."
                        ),
                    })
                    response = self._create_with_retry(messages, tools=False)
                    costs.api_calls += 1
                    costs.input_tokens += response.usage.input_tokens
                    costs.output_tokens += response.usage.output_tokens
                    nudge_text = [b for b in response.content if b.type == "text"]
                    output = nudge_text[-1].text.strip() if nudge_text else "(no output)"
                return output, costs

            if response.stop_reason == "tool_use":
                if tool_call_count >= MAX_TOOL_CALLS:
                    # Execute the pending tool calls to maintain valid message history,
                    # then include a nudge instruction alongside the tool results so
                    # Claude knows to produce structured output on the next turn.
                    messages.append({"role": "assistant", "content": response.content})
                    tool_results = []
                    for block in tool_blocks:
                        result = self._dispatch_tool(block.name, block.input, costs)
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps(result),
                        })
                    # A user turn can mix tool_result and text blocks.
                    tool_results.append({
                        "type": "text",
                        "text": (
                            "That is the last research step allowed. Produce the final "
                            "structured output now based on everything you have found — "
                            "starting with 'classification:'. No other text."
                        ),
                    })
                    messages.append({"role": "user", "content": tool_results})
                    forced = self._create_with_retry(messages, tools=False)
                    costs.api_calls += 1
                    costs.input_tokens += forced.usage.input_tokens
                    costs.output_tokens += forced.usage.output_tokens
                    forced_text = [b for b in forced.content if b.type == "text"]
                    return forced_text[-1].text.strip() if forced_text else "(max tool calls reached)", costs

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
