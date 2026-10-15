"""Merchant identity: the normalisation that keys a merchant in memory, questions and events.

Statements print one merchant with branch numbers and company forms that vary between rows, so
these are dropped; the key is the home finance agent's own and no card agent needs to share it.
"""
from __future__ import annotations

COMPANY_FORMS = frozenset({"בעמ", 'בע"מ', "בע״מ", "ltd", "ltd.", "inc", "inc.", "llc"})


def _strip_trailing_digit_groups(words: list[str]) -> list[str]:
    end = len(words)
    while end > 0 and words[end - 1].isdigit():
        end -= 1
    return words[:end]


def merchant_key(raw: str) -> str:
    """Normalised merchant identity.

    If normalisation removes every word, the collapsed raw text is the key; a blank raw
    merchant is a contract violation and raises ValueError.
    """
    collapsed = " ".join(raw.lower().split())
    if not collapsed:
        raise ValueError("merchant must not be blank")
    words = _strip_trailing_digit_groups(collapsed.split())
    words = [w for w in words if w not in COMPANY_FORMS]
    return " ".join(_strip_trailing_digit_groups(words)) or collapsed
