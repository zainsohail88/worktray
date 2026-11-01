import asyncio
from datetime import datetime, timedelta, timezone
import sqlite3

import pytest

from worktray.engine import Engine
from worktray.models import Batch, SourceState
from worktray.sources.errors import NotConnectedError
from worktray.store import Store

NOW = datetime(2026, 10, 21, 9, 0, tzinfo=timezone.utc)


async def empty() -> Batch:
    return Batch()


@pytest.fixture
def engine(store):
    return Engine(store, {"jira": empty, "slack": empty})


def attempted(engine: Engine, source: str, minutes_ago: int) -> None:
    engine.states[source].last_attempt = (NOW - timedelta(minutes=minutes_ago)).isoformat()


def test_never_attempted_sources_are_due(engine):
    assert engine.due(NOW) == ["jira", "slack"]


def test_source_inside_its_interval_is_not_due(engine):
    attempted(engine, "jira", 9)
    attempted(engine, "slack", 59)

    assert engine.due(NOW) == []


def test_ai_backed_source_waits_longer_than_api_source(engine):
    attempted(engine, "jira", 11)
    attempted(engine, "slack", 11)

    assert engine.due(NOW) == ["jira"]


def test_source_with_schedule_off_is_never_due(engine):
    engine.set_interval("jira", None)

    assert engine.due(NOW + timedelta(days=30)) == ["slack"]


def test_paused_scheduler_has_nothing_due(engine):
    engine.set_auto_refresh(False)

    assert engine.due(NOW) == []


def test_resumed_scheduler_keeps_the_chosen_intervals(engine):
    engine.set_interval("jira", 14400)
    engine.set_auto_refresh(False)
    engine.set_auto_refresh(True)

    assert engine.intervals()["jira"] == 14400


def test_chosen_interval_replaces_the_default(engine):
    engine.set_interval("slack", 7200)
    attempted(engine, "slack", 90)

    assert "slack" not in engine.due(NOW)


def test_running_source_is_not_due(engine):
    engine.states["jira"] = SourceState(source="jira", state="refreshing")

    assert engine.due(NOW) == ["slack"]


@pytest.mark.parametrize("source, seconds", [("nope", 600), ("jira", 5)])
def test_unsupported_interval_is_rejected(engine, source, seconds):
    with pytest.raises(ValueError):
        engine.set_interval(source, seconds)


def test_scheduler_keeps_running_after_a_failed_tick(engine, monkeypatch):
    ticks = []

    def due() -> list[str]:
        ticks.append(1)
        if len(ticks) == 1:
            raise sqlite3.OperationalError("database is locked")
        return ["jira"]

    started = []
    monkeypatch.setattr(engine, "due", due)
    monkeypatch.setattr(engine, "start", lambda sources: started.append(sources) or sources)

    async def run() -> None:
        task = asyncio.create_task(engine.run_schedule(tick=0.01))
        await asyncio.sleep(0.1)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    asyncio.run(run())

    assert started[0] == ["jira"]


def test_chosen_interval_survives_a_restart(engine, tmp_path):
    engine.set_interval("jira", 14400)

    restarted = Engine(Store(tmp_path / "tracker.sqlite3"), {"jira": empty})

    assert restarted.intervals() == {"jira": 14400}


def test_unconfigured_optional_source_is_not_connected_and_not_an_error(tmp_path):
    async def missing() -> Batch:
        raise NotConnectedError("Not connected (optional)")

    engine = Engine(Store(tmp_path / "tracker.sqlite3"), {"teamcity": missing})

    asyncio.run(engine.refresh("teamcity"))

    state = engine.states["teamcity"]
    assert (state.state, state.stale_since) == ("not_connected", None)
