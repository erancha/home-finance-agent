"""Logs one model_call line per answered call of a LangChain chat model.

The same file in every Docker repo whose model is a LangChain chat model.
"""

import time
from collections.abc import Mapping
from typing import Any
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, LLMResult

from .model_costs import Usage, log_model_call, require_price

# Anthropic reports a cache write either as one count or split by the entry's lifetime.
_CACHE_WRITE_KEYS = ("cache_creation", "ephemeral_5m_input_tokens", "ephemeral_1h_input_tokens")


def _count(details: Mapping[str, object], key: str) -> int:
    """A provider leaves out, or sets to None, a count its reply does not report."""
    value = details.get(key)
    if value is None:
        return 0
    assert isinstance(value, int), f"{key} is {value!r}, not a token count"
    return value


class ModelCallLog(BaseCallbackHandler):
    """Attached to one chat model: each answered call logs its usage under the kind given here.
    LangChain counts a call's cached tokens inside input_tokens, for both providers, so they are
    taken out of it to bill each at its own rate. A provider that fails a call bills nothing and
    leaves no line."""

    def __init__(self, spec: str, kind: str):
        require_price(spec)
        self.spec = spec
        self.kind = kind
        # Key: the run id of a call in flight; value: when it started (perf_counter seconds).
        self._started: dict[UUID, float] = {}

    def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[list[BaseMessage]],
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        self._started[run_id] = time.perf_counter()

    def on_llm_end(self, response: LLMResult, *, run_id: UUID, **kwargs: Any) -> None:
        started = self._started.pop(run_id)
        [[generation]] = response.generations
        assert isinstance(generation, ChatGeneration)
        message = generation.message
        assert isinstance(message, AIMessage) and message.usage_metadata is not None, (
            f"{self.spec} answered without token usage"
        )
        usage = message.usage_metadata
        details = usage.get("input_token_details", {})
        read = _count(details, "cache_read")
        written = sum(_count(details, key) for key in _CACHE_WRITE_KEYS)
        billed = Usage(
            usage["input_tokens"] - read - written, usage["output_tokens"], read, written
        )
        log_model_call(self.kind, self.spec, billed, time.perf_counter() - started)

    def on_llm_error(self, error: BaseException, *, run_id: UUID, **kwargs: Any) -> None:
        self._started.pop(run_id)
