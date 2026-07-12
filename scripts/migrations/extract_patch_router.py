from pathlib import Path

ROOT = Path("/srv/lilith")
ASSISTANT_ROUTER = ROOT / "osiris-api/app/assistant_router.py"
PATCH_ROUTER = ROOT / "osiris-api/app/routers/patch_router.py"
ROUTERS_INIT = ROOT / "osiris-api/app/routers/__init__.py"

text = ASSISTANT_ROUTER.read_text()

if "from routers.patch_router import PATCH_COMMANDS, handle_patch_command" in text:
    raise SystemExit("Patch router import already exists. Refusing to patch twice.")

start1_marker = '    if command == "patch_generate_ai":\n'
end1_marker = '    if command == "dev_review_generate_patch":\n'
start2_marker = '    if command == "patch_backups":\n'

if start1_marker not in text:
    raise SystemExit("Could not find patch_generate_ai block. No changes made.")

if end1_marker not in text:
    raise SystemExit("Could not find dev_review_generate_patch marker. No changes made.")

if start2_marker not in text:
    raise SystemExit("Could not find patch_backups block. No changes made.")

start1 = text.index(start1_marker)
end1 = text.index(end1_marker, start1)
start2 = text.index(start2_marker, end1)

# The patch_backups / restore / pending / view/apply/deny block sits near the end.
# Keep the final fallback return in assistant_router.py.
fallback_start = text.rfind('\n    return {\n')
if fallback_start <= start2:
    raise SystemExit("Could not safely find final fallback return. No changes made.")

fallback_start += 1

block1 = text[start1:end1]
block2 = text[start2:fallback_start]

patch_router_text = '''from typing import Any
import re

from approvals import create_approval
from memory import save_memory

from patch_core import (
    list_pending_patches,
    get_patch,
    apply_patch,
    deny_patch,
    generate_patch_with_ai,
    list_patch_backups,
)


PATCH_COMMANDS = {
    "patch_generate_ai",
    "patch_backups",
    "patch_restore_request",
    "patch_pending",
    "patch_view",
    "patch_apply",
    "patch_deny",
}


async def handle_patch_command(command: str, message: str) -> dict[str, Any]:
''' + block1 + "\n" + block2 + '''
    return {
        "type": "tool_result",
        "command": command,
        "answer": f"Patch command was not handled: {command}",
        "data": None,
    }
'''

PATCH_ROUTER.write_text(patch_router_text)
ROUTERS_INIT.touch(exist_ok=True)

replacement = '''    if command in PATCH_COMMANDS:
        return await handle_patch_command(command, message)

'''

new_text = (
    text[:start1]
    + replacement
    + text[end1:start2]
    + text[fallback_start:]
)

import_line = "from routers.patch_router import PATCH_COMMANDS, handle_patch_command\n"

anchor = "from routers.document_router import handle_document_query\n"
if anchor in new_text:
    new_text = new_text.replace(anchor, anchor + import_line, 1)
else:
    new_text = import_line + new_text

ASSISTANT_ROUTER.write_text(new_text)

print("Patch router extracted.")
print(f"Created: {PATCH_ROUTER}")
print("Patched: osiris-api/app/assistant_router.py")
