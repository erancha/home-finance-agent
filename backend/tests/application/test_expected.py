from __future__ import annotations

from datetime import date
from decimal import Decimal

from hfm.application.expected import expected_charges, months_between, with_expected
from hfm.domain.models import CategoryTotal, Installment
from tests.builders import make_tx

GYM = "וים קלאבס 77"


def test_months_between_counts_across_a_year_end() -> None:
    assert months_between("2026-10", "2026-11") == 1
    assert months_between("2026-11", "2027-02") == 3


def test_a_standing_order_not_yet_charged_is_expected_a_month_later() -> None:
    gym = make_tx(
        id="g1", raw_merchant=GYM, standing_order=True, category="health",
        transaction_date=date(2026, 9, 30), charge_date=date(2026, 10, 2),
    )
    [expected] = expected_charges([gym], "2026-10", [], "2026-11")
    assert expected.id == "expected-g1"
    assert expected.amount == gym.amount
    assert expected.category == "health"
    assert expected.transaction_date == date(2026, 10, 30)
    assert expected.charge_date == date(2026, 11, 2)


def test_a_standing_order_already_charged_this_month_is_not_expected() -> None:
    october = make_tx(id="g1", raw_merchant=GYM, standing_order=True)
    november = make_tx(id="g2", raw_merchant="וים קלאבס 81", standing_order=True)
    assert expected_charges([october], "2026-10", [november], "2026-11") == []


def test_the_same_merchant_on_another_card_does_not_count_as_charged() -> None:
    october = make_tx(id="g1", agent="amex", raw_merchant=GYM, standing_order=True)
    november = make_tx(id="g2", agent="visa", raw_merchant=GYM, standing_order=True)
    assert len(expected_charges([october], "2026-10", [november], "2026-11")) == 1


def test_the_next_installment_is_expected_after_the_months_since_the_base() -> None:
    sofa = make_tx(id="s1", installment=Installment(3, 12))
    [expected] = expected_charges([sofa], "2026-09", [], "2026-11")
    assert expected.installment == Installment(5, 12)


def test_an_installment_already_charged_this_month_is_not_expected() -> None:
    october = make_tx(id="s1", installment=Installment(3, 12))
    november = make_tx(id="s2", installment=Installment(4, 12))
    assert expected_charges([october], "2026-10", [november], "2026-11") == []


def test_a_finished_installment_plan_expects_nothing() -> None:
    last = make_tx(id="s1", installment=Installment(12, 12), standing_order=True)
    assert expected_charges([last], "2026-10", [], "2026-11") == []


def test_a_one_off_charge_is_not_expected() -> None:
    assert expected_charges([make_tx()], "2026-10", [], "2026-11") == []


def test_a_charge_date_past_the_target_month_end_is_clamped() -> None:
    late = make_tx(standing_order=True, charge_date=date(2026, 10, 31))
    [expected] = expected_charges([late], "2026-10", [], "2026-11")
    assert expected.charge_date == date(2026, 11, 30)


def test_expected_spend_adds_to_its_category_and_keeps_the_limit() -> None:
    actual = [CategoryTotal("groceries", Decimal("100.00"), Decimal("120.00"))]
    expected = [
        make_tx(category="groceries", amount=Decimal("30.00")),
        make_tx(category="health", amount=Decimal("200.00")),
    ]
    assert with_expected(actual, expected) == [
        CategoryTotal("groceries", Decimal("130.00"), Decimal("120.00")),
        CategoryTotal("health", Decimal("200.00"), None),
    ]
