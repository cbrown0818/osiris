from typing import Any

import httpx

from dev_core import read_file
from patch_core import create_patch


DEV_REVIEW_COMMANDS = {
    "dev_review_generate_patch",
    "dev_review_file",
    "dev_explain_file",
}


async def handle_dev_review_command(command: str, message: str) -> dict[str, Any]:
    if command == "dev_review_generate_patch":
        lowered = message.lower()

        trigger = None
        for phrase in [
            "review and generate patch for ",
            "review and patch file ",
            "review and patch ",
            "generate review patch for ",
        ]:
            if phrase in lowered:
                trigger = phrase
                break

        if not trigger:
            return {
                "type": "tool_result",
                "command": command,
                "answer": "Tell me the file path. Example: review and generate patch for host-agent/host_agent.py",
                "data": None,
            }

        raw_target = message[lowered.find(trigger) + len(trigger):].strip().strip('"').strip("'")

        focus_instruction = "Make one small, safe, practical improvement only."

        focus_markers = [
            " focusing only on ",
            " focus only on ",
            " only ",
            " to ",
        ]

        file_path = raw_target

        for marker in focus_markers:
            if marker in raw_target.lower():
                idx = raw_target.lower().find(marker)
                file_path = raw_target[:idx].strip()
                focus_instruction = raw_target[idx + len(marker):].strip()
                break

        file_data = read_file(file_path, max_bytes=70_000)
        original_content = file_data.get("content", "")

        prompt = (
            "You are improving a source file from the Osiris local AI project.\n\n"
            f"File path: {file_path}\n\n"
            "Task:\n"
            f"Focus instruction: {focus_instruction}\n\n"
            "Make the smallest safe patch that satisfies the focus instruction. "
            "Do not broadly refactor the file. "
            "Do not rewrite unrelated logic. "
            "Do not add risky new features. "
            "Do not remove existing endpoints or core behavior. "
            "Keep behavior compatible unless the focus instruction explicitly says otherwise.\n\n"
            "Return ONLY the complete updated file content. "
            "Do not include markdown fences. Do not explain the change.\n\n"
            "File content:\n"
            "-----BEGIN FILE-----\n"
            f"{original_content}\n"
            "-----END FILE-----\n"
        )

        ollama_url = "http://ollama:11434"

        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                response = await client.post(
                    f"{ollama_url}/api/chat",
                    json={
                        "model": "qwen2.5-coder:7b",
                        "messages": [
                            {
                                "role": "system",
                                "content": "You are a careful senior software engineer. Return only complete updated file contents.",
                            },
                            {
                                "role": "user",
                                "content": prompt,
                            },
                        ],
                        "stream": False,
                    },
                )
                response.raise_for_status()
                data = response.json()
        except Exception as exc:
            return {
                "type": "tool_result",
                "command": command,
                "answer": f"Review patch generation failed while calling Ollama: {type(exc).__name__}: {str(exc) or 'no detail returned'}",
                "data": {
                    "file_path": file_path,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
            }

        proposed_content = data.get("message", {}).get("content", "").strip()

        if proposed_content.startswith("```"):
            lines = proposed_content.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            proposed_content = "\n".join(lines).strip()

        if original_content.endswith("\n") and not proposed_content.endswith("\n"):
            proposed_content += "\n"

        if not proposed_content:
            return {
                "type": "tool_result",
                "command": command,
                "answer": "The model returned empty proposed content. No patch was created.",
                "data": {
                    "file_path": file_path,
                    "model": "qwen2.5-coder:7b",
                },
            }

        patch = create_patch(
            file_path=file_path,
            proposed_content=proposed_content,
            reason=f"Review-generated patch for {file_path}",
        )

        answer = (
            "Review-generated patch created and added to pending patches.\n\n"
            f"Patch ID: {patch.get('id')}\n"
            f"File: {patch.get('file_path')}\n"
            f"Reason: {patch.get('reason')}\n\n"
            f"{patch.get('diff')}\n\n"
            "Review the diff, then apply with:\n"
            f"apply patch {patch.get('id')}"
        )

        return {
            "type": "tool_result",
            "command": command,
            "answer": answer,
            "data": {
                "patch": patch,
                "model": "qwen2.5-coder:7b",
                "file": file_data,
            },
        }

    if command == "dev_review_file":
        lowered = message.lower()

        trigger = None
        for phrase in ["review file ", "audit file ", "check file "]:
            if phrase in lowered:
                trigger = phrase
                break

        if not trigger:
            return {
                "type": "tool_result",
                "command": command,
                "answer": "Tell me the file path. Example: review file osiris-api/app/patch_core.py",
                "data": None,
            }

        file_path = message[lowered.find(trigger) + len(trigger):].strip().strip('"').strip("'")

        file_data = read_file(file_path, max_bytes=45_000)
        content = file_data.get("content", "")

        prompt = (
            "You are reviewing a source file from the Osiris local AI project.\n\n"
            f"File path: {file_path}\n\n"
            "Review this file like a careful senior engineer. Focus on:\n"
            "1. Bugs or likely runtime errors\n"
            "2. Security risks\n"
            "3. Fragile logic or edge cases\n"
            "4. Duplicate or messy code\n"
            "5. Missing validation or approval checks\n"
            "6. Practical cleanup/refactor ideas\n\n"
            "Do not rewrite the whole file. Give clear findings and recommended fixes.\n\n"
            "File content:\n"
            "-----BEGIN FILE-----\n"
            f"{content}\n"
            "-----END FILE-----\n"
        )

        ollama_url = "http://ollama:11434"

        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                response = await client.post(
                    f"{ollama_url}/api/chat",
                    json={
                        "model": "qwen2.5-coder:7b",
                        "messages": [
                            {
                                "role": "system",
                                "content": "You are a careful senior software engineer doing practical code review. Be concise and practical.",
                            },
                            {
                                "role": "user",
                                "content": prompt,
                            },
                        ],
                        "stream": False,
                    },
                )
                response.raise_for_status()
                data = response.json()
        except Exception as exc:
            return {
                "type": "tool_result",
                "command": command,
                "answer": f"Review failed while calling Ollama: {type(exc).__name__}: {str(exc) or 'no detail returned'}",
                "data": {
                    "file_path": file_path,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
            }

        answer = data.get("message", {}).get("content", "").strip() or "No review returned."

        return {
            "type": "tool_result",
            "command": command,
            "answer": answer,
            "data": {
                "file": file_data,
                "model": "qwen2.5-coder:7b",
            },
        }

    if command == "dev_explain_file":
        lowered = message.lower()

        trigger = None
        for phrase in ["explain file ", "summarize file ", "what does file "]:
            if phrase in lowered:
                trigger = phrase
                break

        if not trigger:
            return {
                "type": "tool_result",
                "command": command,
                "answer": "Tell me the file path. Example: explain file osiris-api/app/main.py",
                "data": None,
            }

        file_path = message[lowered.find(trigger) + len(trigger):].strip().strip('"').strip("'")

        # Clean common trailing wording
        for tail in [" do", " contain", " mean"]:
            if file_path.lower().endswith(tail):
                file_path = file_path[:-len(tail)].strip()

        file_data = read_file(file_path, max_bytes=80_000)
        content = file_data.get("content", "")

        prompt = (
            "You are explaining a source file from the Osiris local AI project.\n\n"
            f"File path: {file_path}\n\n"
            "Explain this file in a clear developer-friendly way. Include:\n"
            "1. Main purpose\n"
            "2. Important functions/classes/routes\n"
            "3. How it fits into Osiris\n"
            "4. Risks, fragile areas, or cleanup ideas\n\n"
            "File content:\n"
            "-----BEGIN FILE-----\n"
            f"{content}\n"
            "-----END FILE-----\n"
        )

        ollama_url = "http://ollama:11434"

        async with httpx.AsyncClient(timeout=180.0) as client:
            response = await client.post(
                f"{ollama_url}/api/chat",
                json={
                    "model": "qwen2.5-coder:7b",
                    "messages": [
                        {
                            "role": "system",
                            "content": "You are a careful senior software engineer explaining code clearly and practically.",
                        },
                        {
                            "role": "user",
                            "content": prompt,
                        },
                    ],
                    "stream": False,
                },
            )
            response.raise_for_status()
            data = response.json()

        answer = data.get("message", {}).get("content", "").strip() or "No explanation returned."

        return {
            "type": "tool_result",
            "command": command,
            "answer": answer,
            "data": {
                "file": file_data,
                "model": "qwen2.5-coder:7b",
            },
        }


    return {
        "type": "tool_result",
        "command": command,
        "answer": f"Dev review command was not handled: {command}",
        "data": None,
    }
