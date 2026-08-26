from __future__ import annotations

import re
import sys
from pathlib import Path

root = Path(sys.argv[1]).resolve()
errors: list[str] = []
link_pattern = re.compile(r"(?<!!)\[[^]]+\]\(([^)]+)\)")

for document in (root / "docs").rglob("*.md"):
    for target in link_pattern.findall(document.read_text(encoding="utf-8")):
        target = target.strip().split("#", 1)[0]
        if not target or "://" in target or target.startswith("mailto:"):
            continue
        if not (document.parent / target).resolve().exists():
            errors.append(f"{document.relative_to(root)} -> {target}")

status = (root / "docs" / "CURRENT_STATUS.md").read_text(encoding="utf-8")
for required in ("REV-01R PASSED", "M0R-06", "M0R-07", "CI", "Staging", "Keycloak"):
    if required not in status:
        errors.append(f"CURRENT_STATUS missing: {required}")

index = (root / "docs" / "README.md").read_text(encoding="utf-8")
for required in ("Owner", "CURRENT", "EVIDENCE", "SUPERSEDED", "V2.1", "V3.0", "V4.0"):
    if required not in index:
        errors.append(f"docs/README missing: {required}")

if errors:
    print("DOC CHECK FAILED")
    print("\n".join(errors))
    raise SystemExit(1)

print("DOC CHECK PASSED")
