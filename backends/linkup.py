"""Linkup search backend (linkup-sdk>=0.11.0)."""

import os
from linkup import LinkupClient
from .base import SearchBackend


class LinkupBackend(SearchBackend):
    """
    Search backend powered by Linkup.

    Uses depth="standard" and output_type="searchResults" to get a structured
    list of results comparable to Exa's output format.

    Cost tracking: Linkup's SDK does not currently expose per-request cost in
    the response object. Cost is recorded as 0.0 and noted in the report.
    See https://www.linkup.so/pricing for current rates.
    """

    name = "linkup"

    def __init__(self):
        api_key = os.environ.get("LINKUP_API_KEY")
        if not api_key:
            raise ValueError("LINKUP_API_KEY environment variable not set")
        self._client = LinkupClient(api_key=api_key)

    def search(self, query: str, num_results: int = 5) -> tuple[list[dict], float]:
        """
        Search via Linkup.

        Returns (results, 0.0) — cost is not tracked per-request by the SDK.
        """
        response = self._client.search(
            query=query,
            depth="standard",
            output_type="searchResults",
            max_results=num_results,
        )

        results = []
        raw = getattr(response, "results", None) or []
        for r in raw:
            # Skip image results — only text results have content
            if getattr(r, "type", None) == "image":
                continue
            results.append({
                "url": getattr(r, "url", "") or "",
                "title": getattr(r, "name", "") or "",
                "snippet": (getattr(r, "content", "") or "").strip()[:300],
            })

        return results, 0.0
