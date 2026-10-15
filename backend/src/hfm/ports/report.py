"""Port to the language model that writes the narrative of a finished review."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class ReportWriter(Protocol):
    async def write(self, prompt: str) -> str:
        """Return the generated report text for the prompt; raises when generation fails."""
        ...
