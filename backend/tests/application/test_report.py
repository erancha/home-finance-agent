from decimal import Decimal

from hfm.application.report import report_prompt
from hfm.domain.models import CategoryTotal


def test_prompt_rows_show_whole_amounts_with_thousands_separators() -> None:
    totals = [
        CategoryTotal("housing", Decimal("3536.51"), Decimal(1500)),
        CategoryTotal("dining", Decimal("86.5"), Decimal(80)),
        CategoryTotal("other", Decimal("12.49"), None),
    ]

    prompt = report_prompt("2026-09", "ILS", totals, 3, [])

    assert "housing | 3,537 | 1,500 | OVER" in prompt.splitlines()
    assert "dining | 87 | 80 | OVER" in prompt.splitlines()
    assert "other | 12 | no limit | ok" in prompt.splitlines()
