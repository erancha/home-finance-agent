import pytest
from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import FakeListChatModel
from langchain_openai import ChatOpenAI

from hfm.adapters.report_writer import (
    CANNED_REPORT,
    CannedReportWriter,
    LangChainReportWriter,
    build_report_writer,
)


async def test_canned_writer_returns_its_text_without_numbers() -> None:
    writer = CannedReportWriter()
    assert await writer.write("anything") == CANNED_REPORT
    assert not any(ch.isdigit() for ch in CANNED_REPORT)


async def test_langchain_writer_sends_the_prompt_and_returns_the_reply_text() -> None:
    model = FakeListChatModel(responses=["Dining ran over its budget."])
    writer = LangChainReportWriter(model)

    assert await writer.write("category | spent") == "Dining ran over its budget."


def test_unknown_provider_raises_naming_it() -> None:
    with pytest.raises(ValueError, match="gemini"):
        build_report_writer("gemini:x", api_key="k")


def test_the_api_key_reaches_the_provider_client(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    writer = build_report_writer("anthropic:claude-sonnet-4-5", api_key="explicit-key")
    assert isinstance(writer, LangChainReportWriter)
    model = writer._model
    assert isinstance(model, ChatAnthropic)
    assert model.anthropic_api_key.get_secret_value() == "explicit-key"


def test_gpt5_models_are_asked_for_minimal_reasoning() -> None:
    writer = build_report_writer("openai:gpt-5-nano", api_key="k")
    assert isinstance(writer, LangChainReportWriter)
    model = writer._model
    assert isinstance(model, ChatOpenAI)
    assert model.reasoning_effort == "minimal"


def test_other_openai_models_get_no_reasoning_option() -> None:
    writer = build_report_writer("openai:gpt-4.1-nano", api_key="k")
    assert isinstance(writer, LangChainReportWriter)
    model = writer._model
    assert isinstance(model, ChatOpenAI)
    assert model.reasoning_effort is None
