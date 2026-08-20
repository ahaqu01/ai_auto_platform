from dataclasses import dataclass, field
from enum import StrEnum
from uuid import UUID

from platform_api.common.errors import DomainError


class OrganizationRole(StrEnum):
    OWNER = "OWNER"
    ADMIN = "ADMIN"
    MEMBER = "MEMBER"


@dataclass(slots=True)
class OrganizationMember:
    user_id: UUID
    role: OrganizationRole
    active: bool = True


@dataclass(slots=True)
class Organization:
    id: UUID
    name: str
    members: dict[UUID, OrganizationMember] = field(default_factory=dict)

    def add_member(self, member: OrganizationMember) -> None:
        if member.user_id in self.members:
            raise DomainError("MEMBER_ALREADY_EXISTS", "用户已经是企业成员", 409)
        self.members[member.user_id] = member

    def change_role(self, user_id: UUID, role: OrganizationRole) -> None:
        member = self._member(user_id)
        if member.role is OrganizationRole.OWNER and role is not OrganizationRole.OWNER:
            self._require_another_owner(user_id)
        member.role = role

    def remove_member(self, user_id: UUID) -> None:
        member = self._member(user_id)
        if member.role is OrganizationRole.OWNER:
            self._require_another_owner(user_id)
        del self.members[user_id]

    def _member(self, user_id: UUID) -> OrganizationMember:
        try:
            return self.members[user_id]
        except KeyError as exc:
            raise DomainError("MEMBER_NOT_FOUND", "企业成员不存在", 404) from exc

    def _require_another_owner(self, excluded_user_id: UUID) -> None:
        has_other_owner = any(
            member.active
            and member.user_id != excluded_user_id
            and member.role is OrganizationRole.OWNER
            for member in self.members.values()
        )
        if not has_other_owner:
            raise DomainError("LAST_OWNER_REQUIRED", "企业必须至少保留一名所有者", 409)

