from __future__ import annotations

import pytest

from hfm.domain.merchants import merchant_key


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("סופר פארם בעמ 123", "סופר פארם"),
        ("  AMAZON   MKTPLACE ", "amazon mktplace"),
        ("פז יהוד 0421", "פז יהוד"),
        ('שופרסל בע"מ', "שופרסל"),
        ("שופרסל בע״מ 7", "שופרסל"),
        ("Acme Ltd. 12", "acme"),
        ("Acme INC", "acme"),
        ("Acme LLC 5 6", "acme"),
    ],
)
def test_merchant_key_examples(raw: str, expected: str) -> None:
    assert merchant_key(raw) == expected


def test_merchant_key_never_empty() -> None:
    assert merchant_key("1234") == "1234"
    assert merchant_key("בעמ") == "בעמ"


@pytest.mark.parametrize("raw", ["", "   "])
def test_merchant_key_rejects_blank(raw: str) -> None:
    with pytest.raises(ValueError, match="blank"):
        merchant_key(raw)
