from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from dataclasses import asdict
from datetime import timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import text

from platform_api.db.session import engine, session_factory
from platform_api.modules.artifact.maintenance import ArtifactMaintenanceService
from platform_api.modules.artifact.storage_runtime import build_object_storage
from platform_api.settings import Settings, get_settings

_LOCK_ID = 0x4149504D323037


def _emit(event: str, **fields: Any) -> None:
    print(json.dumps({"event": event, **fields}, sort_keys=True), flush=True)


def _validate(settings: Settings) -> None:
    bounds = {
        "artifact_maintenance_interval_seconds": (1, 86400),
        "artifact_maintenance_timeout_seconds": (1, 3600),
        "artifact_maintenance_batch_size": (1, 1000),
        "artifact_orphan_grace_seconds": (0, 30 * 86400),
        "artifact_maintenance_alert_failure_threshold": (1, 1000),
    }
    for name, (lower, upper) in bounds.items():
        value = int(getattr(settings, name))
        if not lower <= value <= upper:
            raise ValueError(f"{name} must be between {lower} and {upper}")


async def run_iteration(settings: Settings) -> dict[str, Any]:
    _validate(settings)
    storage = build_object_storage(settings)
    if storage is None:
        raise RuntimeError("object storage is not configured")

    async with engine.connect() as connection:
        acquired = bool(
            await connection.scalar(
                text("SELECT pg_try_advisory_lock(:lock_id)"), {"lock_id": _LOCK_ID}
            )
        )
        if not acquired:
            result = {"status": "skipped", "reason": "lock_held"}
            _emit("artifact_maintenance_skipped", **result)
            return result
        try:
            service = ArtifactMaintenanceService(
                session_factory,
                storage,
                batch_size=settings.artifact_maintenance_batch_size,
                orphan_grace=timedelta(
                    seconds=settings.artifact_orphan_grace_seconds
                ),
            )
            started = time.monotonic()
            try:
                async with asyncio.timeout(
                    settings.artifact_maintenance_timeout_seconds
                ):
                    metrics = await service.run_once()
            except TimeoutError:
                _emit(
                    "artifact_maintenance_alert",
                    reason="timeout",
                    timeout_seconds=settings.artifact_maintenance_timeout_seconds,
                )
                raise
            result = {
                "status": "completed",
                "duration_ms": round((time.monotonic() - started) * 1000),
                **asdict(metrics),
            }
            _emit("artifact_maintenance_metrics", **result)
            if metrics.failures >= settings.artifact_maintenance_alert_failure_threshold:
                _emit(
                    "artifact_maintenance_alert",
                    reason="storage_failures",
                    failures=metrics.failures,
                    threshold=settings.artifact_maintenance_alert_failure_threshold,
                )
            Path(settings.artifact_maintenance_heartbeat_path).touch()
            return result
        finally:
            await connection.execute(
                text("SELECT pg_advisory_unlock(:lock_id)"), {"lock_id": _LOCK_ID}
            )


async def run_forever(settings: Settings) -> None:
    consecutive_failures = 0
    while True:
        try:
            await run_iteration(settings)
            consecutive_failures = 0
        except Exception as exc:  # noqa: BLE001 - the scheduler must survive one failed iteration
            consecutive_failures += 1
            _emit(
                "artifact_maintenance_failed",
                error_type=type(exc).__name__,
                consecutive_failures=consecutive_failures,
            )
            if (
                consecutive_failures
                >= settings.artifact_maintenance_alert_failure_threshold
            ):
                _emit(
                    "artifact_maintenance_alert",
                    reason="consecutive_failures",
                    consecutive_failures=consecutive_failures,
                )
        await asyncio.sleep(settings.artifact_maintenance_interval_seconds)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    settings = get_settings()
    if args.once:
        try:
            asyncio.run(run_iteration(settings))
        except Exception as exc:  # noqa: BLE001 - CLI converts any failed iteration to exit 1
            _emit("artifact_maintenance_failed", error_type=type(exc).__name__)
            return 1
        return 0
    try:
        asyncio.run(run_forever(settings))
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
