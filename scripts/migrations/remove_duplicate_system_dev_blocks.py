from pathlib import Path

p = Path("/srv/lilith/osiris-api/app/assistant_router.py")
text = p.read_text()

removals = [
    (
        '    if command == "system_snapshot":\n',
        '    if command == "agent_loop":\n',
    ),
    (
        '    if command == "security_status":\n',
        '    if command == "doc_query":\n',
    ),
]

new_text = text

for start_marker, end_marker in removals:
    if start_marker not in new_text:
        raise SystemExit(f"Missing start marker: {start_marker!r}. No changes made.")
    start = new_text.index(start_marker)

    if end_marker not in new_text[start:]:
        raise SystemExit(f"Missing end marker after {start_marker!r}: {end_marker!r}. No changes made.")
    end = new_text.index(end_marker, start)

    new_text = new_text[:start] + new_text[end:]

if new_text == text:
    raise SystemExit("No changes made.")

p.write_text(new_text)

print("Removed duplicate system/dev legacy blocks.")
print(f"Old lines: {len(text.splitlines())}")
print(f"New lines: {len(new_text.splitlines())}")
