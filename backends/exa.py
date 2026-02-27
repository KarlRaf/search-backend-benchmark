"""Exa search backend (exa-py>=1.0.0)."""

import os
from exa_py import Exa
from .base import SearchBackend


class ExaBackend(SearchBackend):
    """
    Search backend powered by Exa.

    Passes queries verbatim (use_autoprompt disabled) to preserve exact
    query semantics — critical for site: operators and exact-match strings.
    """

    name = "exa"

    def __init__(self):
        api_key = os.environ.get("EXA_API_KEY")
        if not api_key:
            raise ValueError("EXA_API_KEY environment variable not set")
        self._client = Exa(api_key=api_key)

    def search(self, query: str, num_results: int = 5) -> tuple[list[dict], float]:
        """
        Search via Exa with content snippets.

        Cost is read from response.cost_dollars.total when available.
        """
        response = self._client.search(
            query,
            num_results=num_results,
            contents={"text": {"max_characters": 500}},
        )
        results = []
        for r in response.results:
            results.append({
                "url": r.url,
                "title": r.title or "",
                "snippet": (r.text or "").strip(),
            })
        cost = float(response.cost_dollars.total) if response.cost_dollars else 0.0
        return results, cost
