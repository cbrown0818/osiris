from typing import Any
import re

from dev_core import (
    list_tree,
    read_file,
    search_project,
    project_summary,
)


DEV_COMMANDS = {
    "dev_summary",
    "dev_tree",
    "dev_read",
    "dev_search",
}


async def handle_dev_command(command: str, message: str) -> dict[str, Any]:
    if command == "dev_summary":
        data = project_summary()
        answer = (
            "Here is the Osiris project summary. "
            f"Main folders: {', '.join(data.get('folders', []))}. "
            f"Important files: {', '.join(data.get('important_files', [])[:10])}."
        )
        return {"type": "tool_result", "command": command, "answer": answer, "data": data}

    if command == "dev_tree":
        data = list_tree(max_depth=3)
        paths = [item["path"] for item in data.get("items", [])[:40]]
        answer = "Project structure:\n\n" + "\n".join(paths)
        return {"type": "tool_result", "command": command, "answer": answer, "data": data}

    if command == "dev_read":
        lowered = message.lower()

        prefixes = ["read ", "open ", "show file ", "show me file "]
        target = None

        for prefix in prefixes:
            if prefix in lowered:
                start_index = lowered.find(prefix) + len(prefix)
                target = message[start_index:].strip().strip('"').strip("'")
                break

        if not target:
            return {
                "type": "tool_result",
                "command": command,
                "answer": "Tell me the project file path to read, for example: read osiris-api/app/main.py",
                "data": None,
            }

        match = re.search(
            r"[A-Za-z0-9_./-]+\.(?:py|html|css|js|json|ya?ml|md|txt|conf|service|sh|env\.example)",
            target,
        )
        if match:
            target = match.group(0)

        for phrase in [
            " please",
            " for me",
            " and explain it",
            " and summarize it",
            " and show me what is inside",
            " and show me inside",
            " and show it",
        ]:
            if target.lower().endswith(phrase):
                target = target[:-len(phrase)].strip()

        try:
            data = read_file(target, max_bytes=30000)
        except Exception as exc:
            return {
                "type": "tool_result",
                "command": command,
                "answer": f"I could not read that file: {type(exc).__name__}: {str(exc)}",
                "data": {
                    "path": target,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
            }

        answer = f"Read file: {data.get('path')}\n\n" + data.get("content", "")[:6000]
        return {"type": "tool_result", "command": command, "answer": answer, "data": data}

    if command == "dev_search":
        lowered = message.lower()

        query = message
        for prefix in ["find ", "search ", "where is ", "where are "]:
            if prefix in lowered:
                query = message[lowered.find(prefix) + len(prefix):].strip()
                break

        query = query.replace("in my project", "").replace("in osiris", "").strip()

        if not query:
            query = "approval"

        data = search_project(query=query, max_results=25)
        lines = [
            f"{item['path']}:{item['line']} — {item['preview']}"
            for item in data.get("results", [])[:20]
        ]

        answer = f"Search results for: {query}\n\n" + ("\n".join(lines) if lines else "No matches found.")
        return {"type": "tool_result", "command": command, "answer": answer, "data": data}

    return {
        "type": "tool_result",
        "command": command,
        "answer": f"Unknown dev command: {command}",
        "data": None,
    }
