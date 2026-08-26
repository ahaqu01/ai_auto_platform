from pathlib import Path
from typing import get_type_hints

from platform_api.common.public_network import validated_public_addresses

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def test_public_address_validator_declares_tuple_return_type() -> None:
    assert get_type_hints(validated_public_addresses)["return"] == tuple[str, ...]


def test_destroy_confirmation_precedes_disposable_database_creation() -> None:
    source = (
        REPOSITORY_ROOT / "apps/api/tests/postgresql/conftest.py"
    ).read_text(encoding="utf-8")
    fixture_start = source.index("async def disposable_postgresql_database")
    confirmation = source.index(
        "require_database_destroy_confirmation(os.environ)", fixture_start
    )
    create_database = source.index("CREATE DATABASE", fixture_start)
    assert confirmation < create_database
