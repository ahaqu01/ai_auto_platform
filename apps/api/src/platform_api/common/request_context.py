from dataclasses import dataclass
from typing import Literal
from uuid import UUID


@dataclass(frozen=True, slots=True)
class RequestContext:
    actor_type: Literal["USER", "AGENT", "SYSTEM"]
    actor_id: UUID
    organization_id: UUID | None
    project_id: UUID | None
    trace_id: str
    platform_role: str | None = None
    ip_address: str | None = None
