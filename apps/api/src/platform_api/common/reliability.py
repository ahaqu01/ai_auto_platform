import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from platform_api.common.errors import DomainError
from platform_api.db.models import (
    AuditEventModel,
    IdempotencyRecordModel,
    OutboxEventModel,
)


@dataclass(slots=True)
class IdempotencyDecision:
    record: IdempotencyRecordModel
    replay_status: int | None = None
    replay_body: dict[str, Any] | None = None

    @property
    def is_replay(self) -> bool:
        return self.replay_status is not None


def canonical_request_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


async def begin_idempotent_command(
    session: AsyncSession,
    *,
    actor_id: UUID,
    route_key: str,
    idempotency_key: str | None,
    request_payload: dict[str, Any],
) -> IdempotencyDecision:
    if idempotency_key is None:
        raise DomainError("IDEMPOTENCY_KEY_REQUIRED", "必须提供 Idempotency-Key", 428)
    if not 16 <= len(idempotency_key) <= 128:
        raise DomainError(
            "INVALID_IDEMPOTENCY_KEY", "Idempotency-Key 长度必须为 16 到 128", 400
        )
    request_hash = canonical_request_hash(request_payload)
    values = {
        "actor_id": actor_id,
        "route_key": route_key,
        "idempotency_key": idempotency_key,
        "request_hash": request_hash,
        "state": "PROCESSING",
        "expires_at": datetime.now(UTC) + timedelta(hours=24),
    }
    dialect = session.get_bind().dialect.name
    if dialect == "postgresql":
        statement = postgresql_insert(IdempotencyRecordModel)
    elif dialect == "sqlite":
        statement = sqlite_insert(IdempotencyRecordModel)
    else:
        raise RuntimeError(f"idempotency is unsupported for {dialect}")
    inserted = await session.scalar(
        statement.values(**values)
        .on_conflict_do_nothing(
            index_elements=["actor_id", "route_key", "idempotency_key"]
        )
        .returning(IdempotencyRecordModel)
    )
    if inserted is not None:
        return IdempotencyDecision(inserted)
    existing = await session.scalar(
        select(IdempotencyRecordModel).where(
            IdempotencyRecordModel.actor_id == actor_id,
            IdempotencyRecordModel.route_key == route_key,
            IdempotencyRecordModel.idempotency_key == idempotency_key,
        )
    )
    if existing is None:
        raise DomainError("IDEMPOTENCY_IN_PROGRESS", "相同幂等请求正在处理", 409)
    if existing.request_hash != request_hash:
        raise DomainError("IDEMPOTENCY_CONFLICT", "相同幂等键对应了不同请求", 409)
    if (
        existing.state != "COMPLETED"
        or existing.response_status is None
        or existing.response_body is None
    ):
        raise DomainError("IDEMPOTENCY_IN_PROGRESS", "相同幂等请求正在处理", 409)
    return IdempotencyDecision(
        existing, existing.response_status, existing.response_body
    )


def complete_idempotent_command(
    decision: IdempotencyDecision,
    *,
    response_status: int,
    response_body: dict[str, Any],
) -> None:
    decision.record.state = "COMPLETED"
    decision.record.response_status = response_status
    decision.record.response_body = response_body


def record_audit(
    session: AsyncSession,
    *,
    actor_id: UUID,
    action: str,
    resource_type: str,
    resource_id: UUID,
    trace_id: str | None,
    organization_id: UUID | None = None,
    project_id: UUID | None = None,
    detail: dict[str, Any] | None = None,
) -> AuditEventModel:
    event = AuditEventModel(
        organization_id=organization_id,
        project_id=project_id,
        actor_type="USER",
        actor_id=actor_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        result="SUCCESS",
        trace_id=trace_id,
        detail=detail or {},
    )
    session.add(event)
    return event


def record_outbox(
    session: AsyncSession,
    *,
    organization_id: UUID | None,
    aggregate_type: str,
    aggregate_id: UUID,
    event_type: str,
    trace_id: str | None,
    aggregate_version: int,
    payload: dict[str, Any] | None = None,
) -> OutboxEventModel:
    event = OutboxEventModel(
        organization_id=organization_id,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        event_type=event_type,
        payload={
            "schemaVersion": 1,
            "aggregateVersion": aggregate_version,
            "traceId": trace_id,
            "data": payload or {},
        },
    )
    session.add(event)
    return event
