"""Persistence behavior is covered by authenticated tenant API tests.

This module retains direct domain persistence regression for duplicate project codes.
"""

from pathlib import Path

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from platform_api.db.base import Base
from platform_api.db.models import OrganizationModel, ProjectModel


@pytest.mark.asyncio
async def test_project_code_is_unique_inside_organization(tmp_path: Path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'unique.db'}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with factory() as session:
        organization = OrganizationModel(name="测试企业")
        session.add(organization)
        await session.flush()
        session.add_all(
            [
                ProjectModel(
                    organization_id=organization.id,
                    code="vision-demo",
                    name="视觉演示一",
                ),
                ProjectModel(
                    organization_id=organization.id,
                    code="vision-demo",
                    name="视觉演示二",
                ),
            ]
        )
        with pytest.raises(IntegrityError):
            await session.commit()
    await engine.dispose()
