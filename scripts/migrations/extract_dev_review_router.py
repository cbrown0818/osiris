from pathlib import Path

ROOT = Path("/srv/lilith")
ASSISTANT_ROUTER = ROOT / "osiris-api/app/assistant_router.py"
DEV_REVIEW_ROUTER = ROOT / "osiris-api/app/routers/dev_review_router.py"
ROUTERS_INIT = ROOT / "osiris-api/app/routers/__init__.py"

text = ASSISTANT_ROUTER.read_text()

import_line = "from routers.dev_review_router import DEV_REVIEW_COMMANDS, handle_dev_review_command\n"

if import_line in text:
    raise SystemExit("Dev review router import already exists. Refusing to patch twice.")

start_marker = '    if command == "dev_review_generate_patch":\n'

if start_marker not in text:
    raise SystemExit("Could not find dev_review_generate_patch block. No changes made.")

start = text.index(start_marker)

# The dev review/explain block currently runs until the final fallback return.
fallback_start = text.rfind('\n    return {\n')
if fallback_start <= start:
    raise SystemExit("Could not safely find final fallback return. No changes made.")

fallback_start += 1

block = text[start:fallback_start]

dev_review_router_text = '''from typing import Any

import httpx

from dev_core import read_file
from patch_core import create_patch


DEV_REVIEW_COMMANDS = {
    "dev_review_generate_patch",
    "dev_review_file",
    "dev_explain_file",
}


async def handle_dev_review_command(command: str, message: str) -> dict[str, Any]:
''' + block + '''
    return {
        "type": "tool_result",
        "command": command,
        "answer": f"Dev review command was not handled: {command}",
        "data": None,
    }
'''

DEV_REVIEW_ROUTER.write_text(dev_review_router_text)
ROUTERS_INIT.touch(exist_ok=True)

replacement = '''    if command in DEV_REVIEW_COMMANDS:
        return await handle_dev_review_command(command, message)

'''

new_text = text[:start] + replacement + text[fallback_start:]

anchor = "from routers.patch_router import PATCH_COMMANDS, handle_patch_command\n"
if anchor in new_text:
    new_text = new_text.replace(anchor, anchor + import_line, 1)
else:
    new_text = import_line + new_text

ASSISTANT_ROUTER.write_text(new_text)

print("Dev review router extracted.")
print(f"Created: {DEV_REVIEW_ROUTER}")
print("Patched: osiris-api/app/assistant_router.py")
