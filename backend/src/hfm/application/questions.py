"""Builds the questions a paused review puts to the user and validates the answers it gets back.

Core building blocks:
- build_questions: one categorize question per merchant a card agent was unsure of, one per agent
  awaiting input, offering "continue" and "skip"; an agent that names a page for the request gets
  a link to it, where the person resolves the request, while "skip" serves a month whose
  statement does not exist yet; an agent that could not verify the person offers only
  "continue", since the person signs in again and the continue carries the fresh token
- interrupt_payload: the wire form of the questions handed to the caller
- validate_answers: accepts answers to any subset of the categorize questions, since a person
  may not recall every merchant, and requires every remote question; each value must be a legal
  option
- validate_categories: checks categories chosen for merchants of a completed review
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin

from hfm.domain.errors import InvalidAnswersError
from hfm.domain.merchants import merchant_key
from hfm.domain.models import AgentConfig, Transaction
from hfm.domain.questions import (
    CONTINUE,
    SKIP,
    CategorizeQuestion,
    Question,
    RemoteInputQuestion,
    question_to_dict,
)
from hfm.domain.taxonomy import TAXONOMY, UNCATEGORIZED
from hfm.ports import SIGN_IN_REQUIRED, InputRequired

CATEGORY_OPTIONS = tuple(c for c in TAXONOMY if c != UNCATEGORIZED)


@dataclass(frozen=True)
class Answers:
    categories: dict[str, str]
    """Merchant key to chosen category, for the merchants the person answered."""
    remote: dict[str, str]
    """Agent name to the chosen action, one of its question's actions."""


def build_questions(
    unsure: Mapping[str, tuple[Transaction, ...]],
    remote: dict[str, InputRequired],
    agents: Mapping[str, AgentConfig],
) -> list[Question]:
    questions: list[Question] = [
        CategorizeQuestion(f"cat:{key}", key, rows[0].merchant, rows, CATEGORY_OPTIONS)
        for key, rows in unsure.items()
    ]
    questions.extend(
        _remote_question(event, agents[agent]) for agent, event in remote.items()
    )
    return questions


def _remote_question(event: InputRequired, agent: AgentConfig) -> RemoteInputQuestion:
    question_id = f"remote:{agent.name}"
    if event.reason == SIGN_IN_REQUIRED:
        return RemoteInputQuestion(
            question_id, agent.name, event.text, event.reason, None, (CONTINUE,)
        )
    link = None if event.page is None else urljoin(agent.browser_url, event.page)
    return RemoteInputQuestion(
        question_id, agent.name, event.text, event.reason, link, (CONTINUE, SKIP)
    )


def interrupt_payload(questions: list[Question]) -> dict[str, Any]:
    return {"questions": [question_to_dict(q) for q in questions]}


def _allowed_values(question: Question) -> tuple[str, ...]:
    if isinstance(question, CategorizeQuestion):
        return question.options
    return question.actions


def validate_categories(
    transactions: Iterable[Transaction], raw: Mapping[str, Any]
) -> dict[str, str]:
    """Merchant key to category, for keys of the review's merchants and legal categories only."""
    merchants = {merchant_key(t.raw_merchant) for t in transactions}
    unknown = [key for key in raw if key not in merchants]
    invalid = {
        key: f"'{value}' is not one of {', '.join(CATEGORY_OPTIONS)}"
        for key, value in raw.items()
        if key in merchants and value not in CATEGORY_OPTIONS
    }
    if unknown or invalid:
        raise InvalidAnswersError([], unknown, invalid)
    return dict(raw)


def validate_answers(questions: list[Question], raw: Mapping[str, Any]) -> Answers:
    by_id = {q.id: q for q in questions}
    missing = [
        i for i, q in by_id.items() if i not in raw and not isinstance(q, CategorizeQuestion)
    ]
    unknown = [i for i in raw if i not in by_id]
    invalid: dict[str, str] = {}
    for question_id, question in by_id.items():
        if question_id not in raw:
            continue
        value = raw[question_id]
        allowed = _allowed_values(question)
        if not isinstance(value, str):
            invalid[question_id] = f"answer must be a string, got {type(value).__name__}"
        elif value not in allowed:
            invalid[question_id] = f"'{value}' is not one of {', '.join(allowed)}"
    if missing or unknown or invalid:
        raise InvalidAnswersError(missing, unknown, invalid)

    categories: dict[str, str] = {}
    remote: dict[str, str] = {}
    for question_id, question in by_id.items():
        if question_id not in raw:
            continue
        if isinstance(question, CategorizeQuestion):
            categories[question.merchant_key] = raw[question_id]
        else:
            remote[question.agent] = raw[question_id]
    return Answers(categories, remote)
