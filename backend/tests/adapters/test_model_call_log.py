"""Each model call logs one model_call line: its kind, the provider:model, the tokens billed at
each rate and the dollars they cost at the listed prices."""

import json
import logging

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from langchain_core.messages.ai import UsageMetadata

from hfm.adapters.model_call_log import ModelCallLog
from hfm.adapters.model_costs import MODEL_CALL_LOGGER


def answering(spec: str, kind: str, usage: UsageMetadata) -> GenericFakeChatModel:
    reply = AIMessage("ok", usage_metadata=usage)
    return GenericFakeChatModel(messages=iter([reply]), callbacks=[ModelCallLog(spec, kind)])


def logged_lines(caplog: pytest.LogCaptureFixture) -> list[dict]:
    return [json.loads(r.getMessage()) for r in caplog.records if r.name == MODEL_CALL_LOGGER]


@pytest.fixture(autouse=True)
def capture(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger=MODEL_CALL_LOGGER)


async def test_an_anthropic_call_bills_uncached_read_and_written_tokens_apart(
    caplog: pytest.LogCaptureFixture,
) -> None:
    usage = UsageMetadata(
        input_tokens=1500,
        output_tokens=200,
        total_tokens=1700,
        input_token_details={"cache_read": 1000, "cache_creation": 300},
    )
    await answering("anthropic:claude-haiku-5-5", "turn", usage).ainvoke("שלום")

    [line] = logged_lines(caplog)
    assert line == {
        "event": "model_call",
        "kind": "turn",
        "model": "anthropic:claude-haiku-5-5",
        "input_tokens": 200,
        "output_tokens": 200,
        "cache_read_tokens": 1000,
        "cache_write_tokens": 300,
        "seconds": line["seconds"],
        "cost": pytest.approx((200 * 0.10 + 200 * 0.50 + 1000 * 0.01 + 300 * 0.125) / 1e6),
    }


def test_split_cache_writes_count_as_written_tokens(caplog: pytest.LogCaptureFixture) -> None:
    usage = UsageMetadata(
        input_tokens=500,
        output_tokens=10,
        total_tokens=510,
        input_token_details={"cache_read": 0, "ephemeral_5m_input_tokens": 400},
    )
    answering("anthropic:claude-haiku-5-5", "turn", usage).invoke("שלום")

    [line] = logged_lines(caplog)
    assert (line["input_tokens"], line["cache_write_tokens"]) == (100, 400)


def test_an_openai_call_bills_its_cached_prefix_at_the_cached_price(
    caplog: pytest.LogCaptureFixture,
) -> None:
    usage = UsageMetadata(
        input_tokens=1000,
        output_tokens=50,
        total_tokens=1050,
        input_token_details={"cache_read": 800},
    )
    answering("openai:gpt-5-mini", "retry turn", usage).invoke("שלום")

    [line] = logged_lines(caplog)
    assert (line["kind"], line["input_tokens"], line["cache_read_tokens"]) == (
        "retry turn",
        200,
        800,
    )
    assert line["cache_write_tokens"] == 0
    assert line["cost"] == pytest.approx((200 * 0.25 + 50 * 2.00 + 800 * 0.025) / 1e6)


def test_a_model_without_a_listed_price_is_refused() -> None:
    with pytest.raises(ValueError, match="PRICE_PER_MILLION"):
        ModelCallLog("openai:gpt-unlisted", "turn")
