"""Report writers: a canned one for the end-to-end test, and one backed by a LangChain chat
model."""

from __future__ import annotations

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


def build_report_writer(spec: str, api_key: str | None = None) -> ReportWriter:
    """Build the writer for "<provider>:<model>" with an anthropic or openai provider.

    Without an api_key the provider's client reads its own environment variable.
    """
    provider = spec.partition(":")[0]
    if provider not in SUPPORTED_PROVIDERS:
        raise ValueError(f"unsupported report model provider {provider!r} in {spec!r}")
    if api_key is None:
        return LangChainReportWriter(init_chat_model(spec))
    return LangChainReportWriter(init_chat_model(spec, api_key=api_key))
