from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from platform_api.common.errors import DomainError


class ProjectStatus(StrEnum):
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"


@dataclass(slots=True)
class Project:
    id: UUID
    organization_id: UUID
    code: str
    name: str
    status: ProjectStatus = ProjectStatus.ACTIVE

    def archive(self) -> None:
        if self.status is ProjectStatus.ARCHIVED:
            return
        self.status = ProjectStatus.ARCHIVED

    def restore(self) -> None:
        self.status = ProjectStatus.ACTIVE

    def require_writable(self) -> None:
        if self.status is not ProjectStatus.ACTIVE:
            raise DomainError("PROJECT_ARCHIVED", "归档项目不可创建资产或任务", 409)

