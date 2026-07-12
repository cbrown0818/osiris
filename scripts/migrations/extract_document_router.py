from pathlib import Path

ROOT = Path("/srv/lilith")
ASSISTANT_ROUTER = ROOT / "osiris-api/app/assistant_router.py"
DOCUMENT_ROUTER = ROOT / "osiris-api/app/routers/document_router.py"
ROUTERS_INIT = ROOT / "osiris-api/app/routers/__init__.py"

START_MARKER = '    if command == "doc_query":\n'
END_MARKER = '    if command == "patch_generate_ai":\n'

assistant_text = ASSISTANT_ROUTER.read_text()

if "from routers.document_router import handle_document_query" in assistant_text:
    raise SystemExit("Document router import already exists. Refusing to patch twice.")

if START_MARKER not in assistant_text:
    raise SystemExit("Could not find doc_query block start. No changes made.")

if END_MARKER not in assistant_text:
    raise SystemExit("Could not find patch_generate_ai block start. No changes made.")

start = assistant_text.index(START_MARKER)
end = assistant_text.index(END_MARKER, start)

doc_block = assistant_text[start:end]
doc_lines = doc_block.splitlines()

# Remove the outer "if command == ..." line.
body_lines = doc_lines[1:]

# The old block lived inside handle_assistant_command().
# Remove one indentation level so it becomes a standalone function body.
unindented = []
for line in body_lines:
    if line.startswith("    "):
        unindented.append(line[4:])
    else:
        unindented.append(line)

document_router_text = '''from typing import Any

import httpx

from document_ingest import (
    search_documents,
    get_latest_document,
    get_document_intro_chunks,
)


async def handle_document_query(message: str) -> dict[str, Any]:
    command = "doc_query"
''' + "\n".join(unindented).rstrip() + "\n"

DOCUMENT_ROUTER.write_text(document_router_text)
ROUTERS_INIT.touch(exist_ok=True)

replacement = '''    if command == "doc_query":
        return await handle_document_query(message)

'''

assistant_text = assistant_text[:start] + replacement + assistant_text[end:]

import_line = "from routers.document_router import handle_document_query\n"

# Put the import near the other project imports.
if "from document_ingest import search_documents, get_latest_document, get_document_intro_chunks\n" in assistant_text:
    assistant_text = assistant_text.replace(
        "from document_ingest import search_documents, get_latest_document, get_document_intro_chunks\n",
        "from document_ingest import search_documents, get_latest_document, get_document_intro_chunks\n" + import_line,
        1,
    )
else:
    assistant_text = import_line + assistant_text

ASSISTANT_ROUTER.write_text(assistant_text)

print("Document router extracted.")
print(f"Created: {DOCUMENT_ROUTER}")
print("Patched: osiris-api/app/assistant_router.py")
