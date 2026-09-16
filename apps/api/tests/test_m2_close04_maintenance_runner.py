from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest

from platform_api.modules.artifact import maintenance_runner


@dataclass
class Metrics:
    expired_sessions: int = 1
    multipart_aborted: int = 1
    artifacts_deleted: int = 1
    missing_objects: int = 1
    orphan_objects_deleted: int = 1
    failures: int = 0


class Connection:
    def __init__(self, acquired=True):
        self.acquired = acquired
        self.unlocks = 0

    async def scalar(self, _statement, _params):
        return self.acquired

    async def execute(self, _statement, _params):
        self.unlocks += 1


class Engine:
    def __init__(self, connection):
        self.connection = connection

    @asynccontextmanager
    async def connect(self):
        yield self.connection


def settings(tmp_path: Path, **overrides):
    values = {
        "artifact_maintenance_interval_seconds": 1,
        "artifact_maintenance_timeout_seconds": 1,
        "artifact_maintenance_batch_size": 10,
        "artifact_orphan_grace_seconds": 60,
        "artifact_maintenance_alert_failure_threshold": 1,
        "artifact_maintenance_heartbeat_path": str(tmp_path / "heartbeat"),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.asyncio
async def test_iteration_is_mutually_exclusive(monkeypatch, tmp_path):
    connection = Connection(acquired=False)
    monkeypatch.setattr(maintenance_runner, "engine", Engine(connection))
    monkeypatch.setattr(maintenance_runner, "build_object_storage", lambda _s: object())
    result = await maintenance_runner.run_iteration(settings(tmp_path))
    assert result == {"status": "skipped", "reason": "lock_held"}
    assert connection.unlocks == 0


@pytest.mark.asyncio
async def test_iteration_emits_metrics_touches_heartbeat_and_unlocks(
    monkeypatch, tmp_path
):
    connection = Connection()

    class Service:
        def __init__(self, *_args, **_kwargs):
            pass

        async def run_once(self):
            return Metrics()

    monkeypatch.setattr(maintenance_runner, "engine", Engine(connection))
    monkeypatch.setattr(maintenance_runner, "build_object_storage", lambda _s: object())
    monkeypatch.setattr(maintenance_runner, "ArtifactMaintenanceService", Service)
    config = settings(tmp_path)
    result = await maintenance_runner.run_iteration(config)
    assert result["status"] == "completed"
    assert result["orphan_objects_deleted"] == 1
    assert Path(config.artifact_maintenance_heartbeat_path).exists()
    assert connection.unlocks == 1


@pytest.mark.asyncio
async def test_timeout_fails_and_always_releases_lock(monkeypatch, tmp_path):
    connection = Connection()

    class Service:
        def __init__(self, *_args, **_kwargs):
            pass

        async def run_once(self):
            import asyncio

            await asyncio.sleep(2)

    monkeypatch.setattr(maintenance_runner, "engine", Engine(connection))
    monkeypatch.setattr(maintenance_runner, "build_object_storage", lambda _s: object())
    monkeypatch.setattr(maintenance_runner, "ArtifactMaintenanceService", Service)
    with pytest.raises(TimeoutError):
        await maintenance_runner.run_iteration(settings(tmp_path))
    assert connection.unlocks == 1


@pytest.mark.parametrize(
    "name,value",
    [
        ("artifact_maintenance_interval_seconds", 0),
        ("artifact_maintenance_timeout_seconds", 3601),
        ("artifact_maintenance_batch_size", 1001),
        ("artifact_orphan_grace_seconds", -1),
        ("artifact_maintenance_alert_failure_threshold", 0),
    ],
)
def test_configuration_bounds(tmp_path, name, value):
    with pytest.raises(ValueError, match=name):
        maintenance_runner._validate(settings(tmp_path, **{name: value}))
