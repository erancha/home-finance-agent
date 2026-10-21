"""Which card agents are connected, so the page can say so before a review starts."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from hfm.platform.api.auth import CurrentSession
from hfm.platform.dependencies import Deps

router = APIRouter(prefix="/api/agents")


class AgentsResponse(BaseModel):
    agents: list[str]


@router.get("")
async def list_agents(wired: Deps, session: CurrentSession) -> AgentsResponse:
    return AgentsResponse(agents=list(wired.card_agents))
