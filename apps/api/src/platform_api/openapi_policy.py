from __future__ import annotations

from collections.abc import Iterator
from typing import Any

HTTP_METHODS = {"get", "post", "put", "patch", "delete", "options", "head"}
FORBIDDEN_IDENTITY_INPUTS = {"user_id", "actor_id", "subject", "owner_id"}
APPROVED_IDENTITY_INPUT_EXCEPTIONS: set[tuple[str, str, str, str]] = set()


def _resolve_ref(document: dict[str, Any], value: dict[str, Any]) -> dict[str, Any]:
    reference = value.get("$ref")
    if not reference:
        return value
    if not reference.startswith("#/"):
        raise ValueError("external OpenAPI references require explicit review")
    resolved: Any = document
    for part in reference[2:].split("/"):
        resolved = resolved[part.replace("~1", "/").replace("~0", "~")]
    return resolved


def _schema_input_names(
    document: dict[str, Any],
    schema: dict[str, Any],
    seen: frozenset[str] = frozenset(),
) -> Iterator[str]:
    reference = schema.get("$ref")
    if reference:
        if reference in seen:
            return
        yield from _schema_input_names(
            document,
            _resolve_ref(document, schema),
            seen | {reference},
        )
        return

    for name, child in schema.get("properties", {}).items():
        yield name
        yield from _schema_input_names(document, child, seen)
    if isinstance(schema.get("items"), dict):
        yield from _schema_input_names(document, schema["items"], seen)
    for keyword in ("allOf", "anyOf", "oneOf"):
        for child in schema.get(keyword, []):
            yield from _schema_input_names(document, child, seen)


def _operation_input_fields(
    document: dict[str, Any],
    method: str,
    path: str,
    operation: dict[str, Any],
) -> Iterator[tuple[str, str]]:
    path_item = document["paths"][path]
    for parameter in [
        *path_item.get("parameters", []),
        *operation.get("parameters", []),
    ]:
        parameter = _resolve_ref(document, parameter)
        yield parameter["in"], parameter["name"]

    request_body = operation.get("requestBody")
    if request_body:
        request_body = _resolve_ref(document, request_body)
        for media_type in request_body.get("content", {}).values():
            for name in _schema_input_names(document, media_type.get("schema", {})):
                yield "body", name


def _normalize_input_name(name: str) -> str:
    return name.strip().replace("-", "_").casefold()


def forbidden_identity_inputs(
    document: dict[str, Any],
    approved_exceptions: set[tuple[str, str, str, str]] | None = None,
) -> set[tuple[str, str, str, str]]:
    approved = (
        APPROVED_IDENTITY_INPUT_EXCEPTIONS
        if approved_exceptions is None
        else approved_exceptions
    )
    violations: set[tuple[str, str, str, str]] = set()
    for path, path_item in document["paths"].items():
        for method, operation in path_item.items():
            normalized_method = method.lower()
            if normalized_method not in HTTP_METHODS:
                continue
            for location, name in _operation_input_fields(
                document,
                normalized_method,
                path,
                operation,
            ):
                normalized_name = _normalize_input_name(name)
                finding = (normalized_method, path, location, normalized_name)
                if (
                    normalized_name in FORBIDDEN_IDENTITY_INPUTS
                    and finding not in approved
                ):
                    violations.add(finding)
    return violations


def assert_no_forbidden_identity_inputs(document: dict[str, Any]) -> None:
    violations = forbidden_identity_inputs(document)
    if violations:
        details = ", ".join("/".join(item) for item in sorted(violations))
        raise RuntimeError(f"OpenAPI caller identity input policy failed: {details}")
