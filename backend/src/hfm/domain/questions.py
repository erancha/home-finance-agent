"""Questions the review puts to the user when it pauses, and their wire payloads."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, assert_never

from hfm.domain.events import transaction_to_dict
from hfm.domain.models import Transaction

CONTINUE = "continue"
SKIP = "skip"


@dataclass(frozen=True)
class CategorizeQuestion:
    id: str
    merchant_key: str
    merchant: str
    transactions: tuple[Transaction, ...]
    """Every row of the merchant in the review, so the person can recall what each was."""
    options: tuple[str, ...]


@dataclass(frozen=True)
class RemoteInputQuestion:
    id: str
    agent: str
    text: str
    link: str | None
    """The agent's page where the person resolves the request, as a browser opens it."""
    actions: tuple[str, ...]


Question = CategorizeQuestion | RemoteInputQuestion


def question_to_dict(q: Question) -> dict[str, Any]:
    match q:
        case CategorizeQuestion():
            return {
                "id": q.id,
                "kind": "categorize",
                "merchant": q.merchant,
                "transactions": [transaction_to_dict(t) for t in q.transactions],
                "options": list(q.options),
            }
        case RemoteInputQuestion():
            return {
                "id": q.id,
                "kind": "remote-input",
                "agent": q.agent,
                "text": q.text,
                "link": q.link,
                "actions": list(q.actions),
            }
        case _:
            assert_never(q)
