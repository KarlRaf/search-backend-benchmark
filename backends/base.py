"""Abstract interface for search backends."""

from abc import ABC, abstractmethod


class SearchBackend(ABC):
    """
    Common interface for all search backends.

    Any new backend only needs to implement search() — the agent
    and eval runner are fully backend-agnostic.
    """

    name: str  # "exa" or "linkup" — used in output labels

    @abstractmethod
    def search(self, query: str, num_results: int = 5) -> tuple[list[dict], float]:
        """
        Execute a search query.

        Args:
            query: The exact search query string (passed verbatim — no autoprompting).
            num_results: Maximum number of results to return.

        Returns:
            A tuple of (results, cost_dollars) where:
              - results is a list of dicts with keys: url, title, snippet
              - cost_dollars is the search API cost in USD (0.0 if not tracked)
        """
