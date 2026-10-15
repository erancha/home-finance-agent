"""Transactions, totals and question payloads behave as values."""

from __future__ import annotations

from decimal import Decimal

from hfm.domain.events import transaction_to_dict
from hfm.domain.merchants import merchant_key
from hfm.domain.models import CategoryTotal, Installment
from hfm.domain.questions import CategorizeQuestion, RemoteInputQuestion, question_to_dict
from tests.builders import make_tx


def test_with_category_keeps_identity() -> None:
    t = make_tx().with_category("health")
    assert t.category == "health"
    assert t.key == ("amex", "201939841")


def test_category_total_over_only_when_limit_exceeded() -> None:
    assert CategoryTotal("transport", Decimal(250), Decimal(200)).over is True
    assert CategoryTotal("transport", Decimal(150), Decimal(200)).over is False
    assert CategoryTotal("transport", Decimal(150), None).over is False


def test_transaction_to_dict_is_json_safe() -> None:
    d = transaction_to_dict(
        make_tx(
            installment=Installment(3, 10),
            original_amount=Decimal("29.99"),
            original_currency="USD",
        )
    )
    assert d["amount"] == "86.90"
    assert d["originalAmount"] == "29.99"
    assert d["installment"] == {"number": 3, "total": 10}
    assert d["transactionDate"] == "2026-09-05"
    assert d["merchantKey"] == merchant_key(d["rawMerchant"])


def test_question_to_dict_shapes() -> None:
    cq = CategorizeQuestion("q1", "סופר פארם", "Super-Pharm", (make_tx(),), ("health", "other"))
    assert question_to_dict(cq) == {
        "id": "q1",
        "kind": "categorize",
        "merchant": "Super-Pharm",
        "transactions": [transaction_to_dict(make_tx())],
        "options": ["health", "other"],
    }
    rq = RemoteInputQuestion(
        "q2", "amex", "No statement covers 2026-09", "http://localhost:8020/s.html", ("continue",)
    )
    assert question_to_dict(rq) == {
        "id": "q2",
        "kind": "remote-input",
        "agent": "amex",
        "text": "No statement covers 2026-09",
        "link": "http://localhost:8020/s.html",
        "actions": ["continue"],
    }
    unlinked = RemoteInputQuestion("q3", "amex", "Enter the SMS code", None, ("continue", "skip"))
    assert question_to_dict(unlinked)["link"] is None
