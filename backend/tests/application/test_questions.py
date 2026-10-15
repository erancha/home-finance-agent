from __future__ import annotations

from dataclasses import replace

import pytest

from hfm.application.questions import (
    Answers,
    build_questions,
    interrupt_payload,
    validate_answers,
    validate_categories,
)
from hfm.domain.errors import InvalidAnswersError
from hfm.domain.merchants import merchant_key
from hfm.domain.models import AgentConfig, TaskRef
from hfm.domain.questions import CategorizeQuestion, RemoteInputQuestion, question_to_dict
from hfm.domain.taxonomy import TAXONOMY
from hfm.ports import InputRequired
from tests.builders import make_tx

ROWS = (make_tx(id="1"), make_tx(id="2"))
INPUT = InputRequired(
    agent="amex",
    task=TaskRef("amex", "t1", "c1"),
    text="Enter the SMS code",
    reason="auth",
    month="2026-09",
    page=None,
)
STATEMENT_MISSING = replace(
    INPUT, text="No statement covers 2026-09", reason="statement-missing", page="/statements.html"
)
AGENTS = {"amex": AgentConfig("amex", "http://amex-agent:8020", "t", "http://localhost:8020")}


def questions(event: InputRequired = INPUT) -> list[CategorizeQuestion | RemoteInputQuestion]:
    return build_questions({"x": ROWS}, {"amex": event}, AGENTS)


def test_build_questions_ids_and_options() -> None:
    cat, remote = questions()
    assert isinstance(cat, CategorizeQuestion)
    assert (cat.id, cat.merchant_key, cat.merchant, cat.transactions) == (
        "cat:x",
        "x",
        ROWS[0].merchant,
        ROWS,
    )
    assert cat.options == tuple(c for c in TAXONOMY if c != "uncategorized")
    assert remote == RemoteInputQuestion(
        "remote:amex", "amex", "Enter the SMS code", None, ("continue", "skip")
    )


def test_build_questions_links_the_agent_page_on_its_browser_address_and_offers_only_continue(
) -> None:
    _, remote = questions(STATEMENT_MISSING)
    assert remote == RemoteInputQuestion(
        "remote:amex",
        "amex",
        "No statement covers 2026-09",
        "http://localhost:8020/statements.html",
        ("continue",),
    )


def test_validate_answers_rejects_skip_for_a_linked_question() -> None:
    with pytest.raises(InvalidAnswersError) as err:
        validate_answers(questions(STATEMENT_MISSING), {"cat:x": "health", "remote:amex": "skip"})
    assert err.value.invalid == {"remote:amex": "'skip' is not one of continue"}


def test_interrupt_payload_serialises_each_question() -> None:
    qs = questions()
    assert interrupt_payload(qs) == {"questions": [question_to_dict(q) for q in qs]}


def test_validate_answers_rejects_a_missing_remote_answer_and_unknown_ids() -> None:
    with pytest.raises(InvalidAnswersError) as err:
        validate_answers(questions(), {"cat:x": "health", "q9": "health"})
    assert err.value.missing == ["remote:amex"]
    assert err.value.unknown == ["q9"]
    assert err.value.invalid == {}


def test_validate_answers_rejects_bad_option() -> None:
    with pytest.raises(InvalidAnswersError) as err:
        validate_answers(questions(), {"cat:x": "pharmacy", "remote:amex": "retry"})
    assert set(err.value.invalid) == {"cat:x", "remote:amex"}
    assert err.value.missing == [] and err.value.unknown == []


def test_validate_answers_rejects_non_string_value() -> None:
    with pytest.raises(InvalidAnswersError) as err:
        validate_answers(questions(), {"cat:x": 5, "remote:amex": "skip"})
    assert set(err.value.invalid) == {"cat:x"}


def test_validate_answers_accepts_unanswered_categorize_questions() -> None:
    answers = validate_answers(questions(), {"remote:amex": "skip"})
    assert answers == Answers(categories={}, remote={"amex": "skip"})


def test_validate_answers_happy_path() -> None:
    answers = validate_answers(questions(), {"cat:x": "health", "remote:amex": "continue"})
    assert answers == Answers(categories={"x": "health"}, remote={"amex": "continue"})


def test_validate_categories_accepts_review_merchants_with_legal_categories() -> None:
    assert validate_categories(ROWS, {merchant_key(ROWS[0].raw_merchant): "health"}) == {
        merchant_key(ROWS[0].raw_merchant): "health"
    }


def test_validate_categories_names_unknown_merchants_and_bad_categories() -> None:
    key = merchant_key(ROWS[0].raw_merchant)
    with pytest.raises(InvalidAnswersError) as err:
        validate_categories(ROWS, {key: "uncategorized", "nobody": "health"})
    assert err.value.unknown == ["nobody"]
    assert set(err.value.invalid) == {key}
