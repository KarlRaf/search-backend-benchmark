"""RunCosts dataclass and Anthropic pricing constants."""

from dataclasses import dataclass, field

# Anthropic claude-sonnet-4-6 pricing (USD per token)
PRICE_INPUT_PER_TOKEN = 3.00 / 1_000_000
PRICE_OUTPUT_PER_TOKEN = 15.00 / 1_000_000


@dataclass
class RunCosts:
    """Accumulated costs for a single agent run."""

    input_tokens: int = 0
    output_tokens: int = 0
    search_cost_usd: float = 0.0  # backend-agnostic (was exa_dollars in original)
    api_calls: int = 0
    search_calls: int = 0

    @property
    def anthropic_cost_usd(self) -> float:
        return (
            self.input_tokens * PRICE_INPUT_PER_TOKEN
            + self.output_tokens * PRICE_OUTPUT_PER_TOKEN
        )

    @property
    def total_cost_usd(self) -> float:
        return self.anthropic_cost_usd + self.search_cost_usd

    def summary(self, backend_name: str = "search") -> str:
        lines = [
            "--- cost summary ---",
            f"  anthropic : {self.api_calls} API calls  |  "
            f"{self.input_tokens:,} input + {self.output_tokens:,} output tokens  |  "
            f"${self.anthropic_cost_usd:.4f}",
            f"  {backend_name:<9}: {self.search_calls} searches  |  ${self.search_cost_usd:.4f}",
            f"  total     : ${self.total_cost_usd:.4f}",
        ]
        return "\n".join(lines)
