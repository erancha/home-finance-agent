from decimal import Decimal

from langgraph.checkpoint.base import empty_checkpoint
from langgraph.checkpoint.memory import InMemorySaver

from hfm.application.review_graph import checkpoint_serde
from hfm.domain.models import TaskRef
from hfm.platform.checkpointer import libpq_dsn, open_checkpointer


def test_libpq_dsn_drops_driver_suffix() -> None:
    assert libpq_dsn("postgresql+psycopg://u:p@h:5434/d") == "postgresql://u:p@h:5434/d"


async def test_checkpoint_round_trip_through_postgres(pg_url: str) -> None:
    checkpoint = empty_checkpoint()
    config = {"configurable": {"thread_id": "t-1", "checkpoint_ns": ""}}
    async with open_checkpointer(libpq_dsn(pg_url)) as saver:
        stored = await saver.aput(
            config, checkpoint, {"source": "input", "step": 0, "parents": {}}, {}
        )
        tuple_ = await saver.aget_tuple(stored)
    assert tuple_ is not None
    assert tuple_.checkpoint["id"] == checkpoint["id"]


async def test_checkpoint_serde_restores_decimal_and_domain_values(pg_url: str) -> None:
    task = TaskRef(agent="amex", task_id="task-1", context_id="ctx-1")
    checkpoint = empty_checkpoint()
    checkpoint["channel_values"] = {"spent": Decimal("86.90"), "task": task}
    versions = {"spent": "1", "task": "1"}
    checkpoint["channel_versions"] = versions
    config = {"configurable": {"thread_id": "t-serde", "checkpoint_ns": ""}}
    async with open_checkpointer(libpq_dsn(pg_url)) as saver:
        stored = await saver.aput(
            config, checkpoint, {"source": "input", "step": 0, "parents": {}}, versions
        )
        restored = await saver.aget_tuple(stored)
    assert restored is not None
    values = restored.checkpoint["channel_values"]
    assert values["spent"] == Decimal("86.90")
    assert isinstance(values["spent"], Decimal)
    assert values["task"] == task


async def _round_trip_task(saver: InMemorySaver, task: TaskRef) -> object:
    checkpoint = empty_checkpoint()
    checkpoint["channel_values"] = {"task": task}
    checkpoint["channel_versions"] = {"task": "1"}
    config = {"configurable": {"thread_id": "t-strict", "checkpoint_ns": ""}}
    stored = await saver.aput(
        config, checkpoint, {"source": "input", "step": 0, "parents": {}}, {"task": "1"}
    )
    restored = await saver.aget_tuple(stored)
    assert restored is not None
    return restored.checkpoint["channel_values"]["task"]


async def test_default_serde_loses_the_task_but_the_allow_list_restores_it() -> None:
    task = TaskRef(agent="amex", task_id="task-1", context_id="ctx-1")
    lost = await _round_trip_task(InMemorySaver(), task)
    kept = await _round_trip_task(InMemorySaver(serde=checkpoint_serde()), task)

    assert type(lost) is dict
    assert lost == {"agent": "amex", "task_id": "task-1", "context_id": "ctx-1"}
    assert type(kept) is TaskRef
    assert kept == task
