"""Report writers: a canned one for the end-to-end test, and one backed by a LangChain chat
model."""

from __future__ import annotations

from typing import Any

from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel

from hfm.ports import ReportWriter

CANNED_REPORT = "This is a canned summary the end-to-end test shows instead of a model's review."
SUPPORTED_PROVIDERS = ("anthropic", "openai")


class CannedReportWriter:
    async def write(self, prompt: str) -> str:
        return CANNED_REPORT


class LangChainReportWriter:
    def __init__(self, model: BaseChatModel) -> None:
        self._model = model

    async def write(self, prompt: str) -> str:
        message = await self._model.ainvoke(prompt)
        return message.text


def build_report_writer(spec: str, api_key: str) -> ReportWriter:
    """Build the writer for "<provider>:<model>" with an anthropic or openai provider.

    The report only phrases totals computed in code, so a model that reasons before answering is
    asked for its least effort: OpenAI's GPT-5 family takes well over a minute on the default.
    """
    provider, _, model = spec.partition(":")
    if provider not in SUPPORTED_PROVIDERS:
        raise ValueError(f"unsupported report model provider {provider!r} in {spec!r}")
    options: dict[str, Any] = {"api_key": api_key}
    if provider == "openai" and model.startswith("gpt-5"):
        options["reasoning_effort"] = "minimal"
    return LangChainReportWriter(init_chat_model(spec, **options))
