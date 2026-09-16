import pytest

from platform_api.api.artifacts import _decode_cursor, _safe_download_name, _version
from platform_api.common.errors import DomainError


def test_invalid_cursor_and_version_headers_are_rejected() -> None:
    with pytest.raises(DomainError) as cursor_error:
        _decode_cursor("not-a-valid-cursor")
    assert cursor_error.value.code == "INVALID_CURSOR"

    with pytest.raises(DomainError) as missing_version:
        _version(None)
    assert missing_version.value.code == "IF_MATCH_REQUIRED"

    with pytest.raises(DomainError) as malformed_version:
        _version("not-an-etag")
    assert malformed_version.value.code == "INVALID_IF_MATCH"

    with pytest.raises(DomainError) as non_numeric_version:
        _version('"abc"')
    assert non_numeric_version.value.code == "INVALID_IF_MATCH"


def test_download_name_removes_paths_quotes_and_empty_values() -> None:
    assert _safe_download_name('../folder/evil".zip') == "evil_.zip"
    assert _safe_download_name("/") == "artifact.bin"
