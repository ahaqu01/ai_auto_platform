"""Export the FastAPI runtime schema as the controlled OpenAPI contract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from platform_api.main import create_app

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = REPOSITORY_ROOT / "packages" / "contracts" / "openapi.json"


def render_openapi() -> str:
    """Return a stable, human-readable representation of the runtime schema."""
    return (
        json.dumps(
            create_app().openapi(),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def export_openapi(output: Path = DEFAULT_OUTPUT) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_openapi(), encoding="utf-8")


def check_openapi(output: Path = DEFAULT_OUTPUT) -> bool:
    return output.exists() and output.read_text(encoding="utf-8") == render_openapi()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if the snapshot is stale")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    output = args.output.resolve()
    if args.check:
        if check_openapi(output):
            print(f"OpenAPI snapshot is current: {output}")
            return 0
        print(f"OpenAPI snapshot is missing or stale: {output}")
        return 1

    export_openapi(output)
    print(f"Exported OpenAPI snapshot: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
