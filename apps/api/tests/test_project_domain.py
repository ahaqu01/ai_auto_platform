from uuid import uuid4

import pytest

from platform_api.common.errors import DomainError
from platform_api.modules.project import Project, ProjectStatus


def test_archived_project_is_read_only() -> None:
    project = Project(uuid4(), uuid4(), "P-001", "Test")
    project.archive()

    with pytest.raises(DomainError) as captured:
        project.require_writable()

    assert captured.value.code == "PROJECT_ARCHIVED"


def test_project_can_be_restored() -> None:
    project = Project(uuid4(), uuid4(), "P-001", "Test")
    project.archive()
    project.restore()
    project.require_writable()
    assert project.status is ProjectStatus.ACTIVE
