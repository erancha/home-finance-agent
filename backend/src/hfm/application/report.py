"""The prompt that asks the language model to narrate a finished review."""
from __future__ import annotations

from collections.abc import Sequence
from decimal import ROUND_HALF_UP, Decimal

from hfm.domain.models import CategoryTotal

INSTRUCTION = (
    "Write 3-5 sentences for a household reviewing its month. Mention every category marked "
    "OVER by name. Use only the numbers in the table above; do not invent numbers."
)


def whole_text(amount: Decimal) -> str:
    """An amount rounded to whole units with thousands separators, as the page shows it; the
    model quotes the table, so the report reads the same way."""
    return f"{amount.quantize(Decimal(1), rounding=ROUND_HALF_UP):,}"


def report_prompt(
    month: str,
    currency: str,
    totals: list[CategoryTotal],
    transaction_count: int,
    skipped: Sequence[str],
) -> str:
    rows = [
        f"{t.category} | {whole_text(t.spent)} | "
        f"{'no limit' if t.limit is None else whole_text(t.limit)} | "
        f"{'OVER' if t.over else 'ok'}"
        for t in totals
    ]
    instruction = INSTRUCTION
    if skipped:
        instruction += (
            f" The following card agents were skipped and their spend is missing: "
            f"{', '.join(skipped)}; say so plainly in the first sentence."
        )
    return "\n".join([
        f"Budget review for {month}: {transaction_count} transactions, amounts in {currency}.",
        "",
        "category | spent | limit | status",
        *rows,
        "",
        instruction,
    ])
