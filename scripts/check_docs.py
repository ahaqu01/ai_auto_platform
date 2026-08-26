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

status_path = root / "docs" / "CURRENT_STATUS.md"
status = status_path.read_text(encoding="utf-8")
if not status.startswith("# Current Status\n"):
    errors.append("CURRENT_STATUS must start with '# Current Status'")
for field in ("Owner", "Updated", "Status"):
    if not re.search(rf"^> {field}[：:].+$", status, re.MULTILINE):
        errors.append(f"CURRENT_STATUS missing metadata: {field}")
if "## 权威执行顺序" not in status:
    errors.append("CURRENT_STATUS missing authoritative execution order")

index = (root / "docs" / "README.md").read_text(encoding="utf-8")
for field in ("Owner", "版本", "状态", "更新日期"):
    if not re.search(rf"^> {field}[：:].+$", index, re.MULTILINE):
        errors.append(f"docs/README missing metadata: {field}")
for state in ("CURRENT", "EVIDENCE", "SUPERSEDED", "DRAFT"):
    if f"`{state}`" not in index:
        errors.append(f"docs/README missing state definition: {state}")

if errors:
    print("DOC CHECK FAILED")
    print("\n".join(errors))
    raise SystemExit(1)

print("DOC CHECK PASSED")
