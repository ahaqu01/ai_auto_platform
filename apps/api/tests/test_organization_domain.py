from uuid import uuid4

import pytest

from platform_api.common.errors import DomainError
from platform_api.modules.organization import (
    Organization,
    OrganizationMember,
    OrganizationRole,
)


def test_cannot_remove_last_owner() -> None:
    owner_id = uuid4()
    organization = Organization(id=uuid4(), name="Test")
    organization.add_member(OrganizationMember(owner_id, OrganizationRole.OWNER))

    with pytest.raises(DomainError) as captured:
        organization.remove_member(owner_id)

    assert captured.value.code == "LAST_OWNER_REQUIRED"


def test_owner_can_be_removed_after_second_owner_added() -> None:
    first = uuid4()
    second = uuid4()
    organization = Organization(id=uuid4(), name="Test")
    organization.add_member(OrganizationMember(first, OrganizationRole.OWNER))
    organization.add_member(OrganizationMember(second, OrganizationRole.OWNER))

    organization.remove_member(first)

    assert first not in organization.members
    assert organization.members[second].role is OrganizationRole.OWNER
