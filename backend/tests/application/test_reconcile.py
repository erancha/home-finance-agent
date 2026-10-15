from __future__ import annotations

from decimal import Decimal

import pytest

from hfm.application.reconcile import (
    apply_memory,
    merge_dict,
    merge_transactions,
    standing_orders,
    totals,
    unsure_merchants,
)
from hfm.domain.models import Budget, CategoryTotal, Confidence
from hfm.domain.taxonomy import TAXONOMY
from tests.builders import make_tx


def test_transactions_reducer_dedupes_by_agent_and_id() -> None:
    amex = make_tx(agent="amex", id="1")
    visa = make_tx(agent="visa", id="1")
    later = make_tx(agent="amex", id="1", category="health")
    merged = merge_transactions([amex, visa], [later])
    assert merged == [later, visa]
    assert len(merge_transactions([], [amex, visa])) == 2


def test_merge_dict_none_removes() -> None:
    existing = {"a": 1, "b": 2}
    assert merge_dict(existing, {"a": None, "c": 3}) == {"b": 2, "c": 3}
    assert existing == {"a": 1, "b": 2}


def test_apply_memory_overrides_the_agent_category() -> None:
    unknown = make_tx(id="1", raw_merchant="סופר פארם בעמ 123")
    already = make_tx(id="2", raw_merchant="סופר פארם בעמ 9", category="groceries")
    other = make_tx(id="3", raw_merchant="Other 1")
    result = apply_memory([unknown, already, other], {"סופר פארם": "health"})
    assert [t.category for t in result] == ["health", "health", "uncategorized"]


def test_totals_sum_decimals_and_mark_overruns() -> None:
    txs = [
        make_tx(id="1", category="transport", amount=Decimal("100.10")),
        make_tx(id="2", category="transport", amount=Decimal("149.90")),
        make_tx(id="3", category="gifts", amount=Decimal("0.10")),
        make_tx(id="4", category="gifts", amount=Decimal("0.20")),
    ]
    budget = Budget("ILS", {"transport": Decimal(200), "dining": Decimal(800)})
    result = totals(txs, budget)
    assert result == [
        CategoryTotal("dining", Decimal(0), Decimal(800)),
        CategoryTotal("transport", Decimal("250.00"), Decimal(200)),
        CategoryTotal("gifts", Decimal("0.30"), None),
    ]
    assert result[1].over
    assert not result[0].over
    order = [t.category for t in result]
    assert order == sorted(order, key=TAXONOMY.index)


def test_unsure_merchants_groups_uncategorized_and_low_confidence_rows_by_key() -> None:
    first = make_tx(id="1", raw_merchant="סופר פארם בעמ 123")
    second = make_tx(id="2", raw_merchant="סופר פארם בעמ 456")
    guessed = make_tx(id="3", raw_merchant="Amazon 1", category="shopping",
                      confidence=Confidence.LOW)
    medium = make_tx(id="4", raw_merchant="Gett", category="transport",
                     confidence=Confidence.MEDIUM)
    sure = make_tx(id="5", raw_merchant="Paz", category="transport")
    assert unsure_merchants([first, second, guessed, medium, sure]) == {
        "סופר פארם": (first, second),
        "amazon": (guessed,),
    }


def test_a_remembered_category_overrules_and_keeps_the_agent_confidence() -> None:
    guessed = make_tx(raw_merchant="Amazon 1", category="shopping", confidence=Confidence.LOW)
    [remembered] = apply_memory([guessed], {"amazon": "gifts"})
    assert (remembered.category, remembered.confidence, remembered.chosen) == (
        "gifts", Confidence.LOW, True
    )
    assert unsure_merchants([remembered]) == {}


def test_totals_rejects_unknown_category() -> None:
    with pytest.raises(ValueError, match="pharmacy"):
        totals([make_tx(category="pharmacy")], Budget("ILS", {}))


def test_standing_orders_sum_only_the_standing_order_rows() -> None:
    rows = [
        make_tx(id="1", amount=Decimal("308.00"), standing_order=True, category="health"),
        make_tx(id="2", amount=Decimal("49.90"), standing_order=True, category="utilities"),
        make_tx(id="3", amount=Decimal("120.00")),
    ]
    assert standing_orders(rows) == Decimal("357.90")
    assert standing_orders([]) == Decimal(0)
