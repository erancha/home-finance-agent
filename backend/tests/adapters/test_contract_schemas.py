"""The published schemas agree with the client: what the client accepts validates, what it
refuses fails. The schemas live in docs/a2a-contract/ at the repository root, beside backend/."""
import json
from pathlib import Path

import pytest
from a2a.helpers import get_data_parts
from jsonschema import Draft202012Validator, ValidationError

from hfm.adapters.a2a_client import _request_message, parse_transaction
from hfm.domain.models import TaskRef
from hfm.domain.taxonomy import TAXONOMY
from tests.builders import ROW, STATEMENT_MISSING_DATA, transactions_batch

SCHEMAS = Path(__file__).parents[3] / "docs" / "a2a-contract"

def validator(name: str) -> Draft202012Validator:
    schema = json.loads((SCHEMAS / name).read_text())
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER)

def batch_of(*rows: dict[str, object]) -> dict[str, object]:
    return transactions_batch("2026-10", list(rows))

def test_schema_ids_are_the_raw_github_urls() -> None:
    for name in ("request", "rows", "pause"):
        schema = json.loads((SCHEMAS / f"{name}.schema.json").read_text())
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert schema["$id"] == ("https://raw.githubusercontent.com/erancha/home-finance-agent/"
                                 f"main/docs/a2a-contract/{name}.schema.json")

def test_a_row_the_client_accepts_validates() -> None:
    validator("rows.schema.json").validate(batch_of(ROW))
    parse_transaction("amex", ROW)

def test_an_empty_batch_validates() -> None:
    validator("rows.schema.json").validate(batch_of())

def test_the_schema_enumerates_the_taxonomy_and_the_three_confidences() -> None:
    schema = json.loads((SCHEMAS / "rows.schema.json").read_text())
    row = schema["$defs"]["transaction"]["properties"]
    assert tuple(row["category"]["enum"]) == TAXONOMY
    assert row["confidence"]["enum"] == ["high", "medium", "low"]

@pytest.mark.parametrize("field,value", [
    ("category", "fuel"), ("confidence", 0.9), ("confidence", "sure"), ("amount", "86.90"),
    ("installment", {}), ("installment", {"number": "3", "total": 10}),
    ("transactionDate", "04/09/2026"), ("transactionDate", "2026-13-45"),
    ("chargeDate", "2026-02-30"), ("transactionDate", "2026-09-04\n"),
])
def test_rows_the_schema_refuses(field: str, value: object) -> None:
    row = {**ROW, field: value}
    with pytest.raises(ValidationError):
        validator("rows.schema.json").validate(batch_of(row))

def test_a_foreign_currency_code_must_be_upper_case() -> None:
    row = {**ROW, "originalAmount": 10.0, "originalCurrency": "usd"}
    with pytest.raises(ValidationError):
        validator("rows.schema.json").validate(batch_of(row))

@pytest.mark.parametrize("month", ["2026-10\n", "2026-13"])
def test_a_batch_month_the_schema_refuses(month: str) -> None:
    with pytest.raises(ValidationError):
        validator("rows.schema.json").validate({**batch_of(), "month": month})

def test_a_batch_over_twenty_five_rows_is_refused() -> None:
    with pytest.raises(ValidationError):
        validator("rows.schema.json").validate(batch_of(*[ROW] * 26))

@pytest.mark.parametrize("date", ["2026-13-45", "2026-09-04\n"])
def test_a_default_validator_refuses_bad_dates_through_the_pattern(date: str) -> None:
    schema = json.loads((SCHEMAS / "rows.schema.json").read_text())
    with pytest.raises(ValidationError):
        Draft202012Validator(schema).validate(batch_of({**ROW, "transactionDate": date}))

def test_a_row_missing_a_field_fails_both_sides() -> None:
    row = {k: v for k, v in ROW.items() if k != "abroad"}
    with pytest.raises(ValidationError):
        validator("rows.schema.json").validate(batch_of(row))
    with pytest.raises(KeyError):
        parse_transaction("amex", row)

def test_an_extra_field_is_allowed_by_both_sides() -> None:
    row = {**ROW, "cardLastDigits": "5509"}
    validator("rows.schema.json").validate(batch_of(row))
    parse_transaction("amex", row)

@pytest.mark.parametrize("data", [{"month": "2026-10"}, {"action": "continue"}])
def test_requests_the_schema_accepts(data: dict[str, object]) -> None:
    validator("request.schema.json").validate(data)

def test_the_requests_the_client_builds_validate() -> None:
    ref = TaskRef(agent="amex", task_id="t", context_id="c")
    for message in (_request_message("2026-10", None), _request_message("2026-10", ref)):
        [data] = get_data_parts(message.parts)
        validator("request.schema.json").validate(data)

@pytest.mark.parametrize("data", [
    {"month": "2026-9"}, {"month": "10/2026"}, {"month": "2026-10\n"}, {"action": "retry"},
    {"month": "2026-10", "action": "continue"}, {},
])
def test_requests_the_schema_refuses(data: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        validator("request.schema.json").validate(data)

def test_the_client_fixture_pause_validates() -> None:
    validator("pause.schema.json").validate(STATEMENT_MISSING_DATA)

@pytest.mark.parametrize("data", [
    {"reason": "statement-missing", "month": "2026-09", "page": "/statements.html", "user": "1000"},
    {"reason": "statement-missing", "month": "2026-09", "user": "1000"},
    {"reason": "sign-in-required", "month": "2026-09", "user": ""},
])
def test_pauses_the_schema_accepts(data: dict[str, object]) -> None:
    validator("pause.schema.json").validate(data)

@pytest.mark.parametrize("data", [
    {"reason": "statement-missing", "month": "2026-09", "page": "http://x/s.html", "user": "1"},
    {"reason": "statement-missing", "month": "2026-09", "page": "//evil", "user": "1"},
    {"reason": "token-expired", "month": "2026-09", "user": ""},
    {"month": "2026-09", "user": "1"},
    {"reason": "statement-missing", "month": "2026-09\n", "user": "1"},
    {"reason": "statement-missing", "month": "2026-09"},
])
def test_pauses_the_schema_refuses(data: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        validator("pause.schema.json").validate(data)
