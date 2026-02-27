"""Linkup search backend (linkup-sdk>=0.12.0)."""

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
    See https://docs.linkup.so for pricing details.
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
            q=query,
            depth="standard",
            output_type="searchResults",
        )

        results = []
        raw = getattr(response, "results", None) or []
        for r in raw[:num_results]:
            results.append({
                "url": getattr(r, "url", "") or "",
                "title": getattr(r, "name", "") or "",
                "snippet": (getattr(r, "content", "") or "").strip()[:500],
            })

        # Cost not exposed by SDK — return 0.0 with a note logged at report time
        return results, 0.0
