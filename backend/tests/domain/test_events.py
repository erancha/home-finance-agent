"""Event type names are the contract the frontend and the SSE route key on."""
from __future__ import annotations

from decimal import Decimal

from hfm.domain import events
from hfm.domain.events import money_text, total_to_dict
from hfm.domain.models import CategoryTotal


def test_event_types_are_the_published_names() -> None:
    assert events.AGENT_DISCOVERED == "agent.discovered"
    assert events.AGENT_STATUS == "agent.status"
    assert events.TRANSACTIONS_BATCH == "transactions.batch"
    assert events.REVIEW_QUESTION == "review.question"
    assert events.REVIEW_TOTALS == "review.totals"
    assert events.REVIEW_WRITING == "review.writing"
    assert events.REVIEW_REPORT == "review.report"
    assert events.REVIEW_FAILED == "review.failed"
    assert events.REVIEW_STATUS == "review.status"


def test_money_text_always_has_two_decimal_places() -> None:
    assert money_text(Decimal("86.9")) == "86.90"
    assert money_text(Decimal(800)) == "800.00"
    assert money_text(Decimal("12.34")) == "12.34"


def test_totals_render_spent_and_limit_as_money_text() -> None:
    total = total_to_dict(CategoryTotal("dining", Decimal("86.9"), Decimal(800)))
    assert total == {"category": "dining", "spent": "86.90", "limit": "800.00", "over": False}
