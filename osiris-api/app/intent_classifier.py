from typing import Literal
import json
import httpx


ALLOWED_COMMANDS = {
    "chat",
    "cognition",
    "agent_loop",
    "self_heal",
    "system_snapshot",
    "security_status",
    "host_summary",
    "system_status",
    "gpu_status",
    "docker_status",
    "dev_summary",
    "dev_tree",
    "dev_read",
    "dev_search",
    "doc_query",
    "dev_review_file",
    "dev_explain_file",
    "dev_review_generate_patch",
    "patch_generate_ai",
    "patch_pending",
    "patch_view",
    "patch_apply",
    "patch_deny",
    "patch_backups",
    "patch_restore_request",
}


async def classify_intent_with_ai(message: str, fallback_command: str = "chat") -> str:
    """
    Uses local Ollama to classify a user message into a Osiris command.
    Falls back safely if Ollama fails or returns nonsense.
    """

    text = message.lower().strip()

    if any(x in text for x in [
        "full system snapshot",
        "complete system snapshot",
        "full os awareness",
        "check everything",
    ]):
        return "system_snapshot"

    if text.startswith("self heal file "):
        return "self_heal"

    # Explicit autonomous execution language stays approval-gated.
    if any(x in text for x in [
        "run agent",
        "autonomously",
    ]):
        return "agent_loop"

    # Analysis and reasoning language defaults to planning only.
    if any(x in text for x in [
        "think through",
        "fully analyze",
        "deep analyze",
        "optimize my codebase",
        "analyze my codebase",
        "analyze project",
        "inspect project",
        "optimize the codebase",
        "review my whole project",
    ]):
        return "cognition"

    # Fast deterministic commands. No Ollama call needed.
    exact_map = {
        "show pending patches": "patch_pending",
        "pending patches": "patch_pending",
        "list patches": "patch_pending",
        "show patches": "patch_pending",
        "show gpu status": "gpu_status",
        "gpu status": "gpu_status",
        "show docker status": "docker_status",
        "docker status": "docker_status",
        "security status": "security_status",
        "system status": "system_status",
        "show memory": "chat",
    }

    if text in exact_map:
        return exact_map[text]

    document_question_markers = [
        "according to the document",
        "according to the pdf",
        "in the document",
        "in the pdf",
        "from the document",
        "from the pdf",
        "what did it say",
        "did you read it",
        "what does the book say",
        "what does the pdf say",
    ]

    if any(marker in text for marker in document_question_markers):
        return "doc_query"

    if text.startswith("ask document ") or text.startswith("search document "):
        return "doc_query"

    if text.startswith("read ") or text.startswith("open "):
        return "dev_read"

    if text.startswith("search ") or text.startswith("find ") or text.startswith("where is "):
        return "dev_search"

    if text.startswith("review file ") or text.startswith("audit file ") or text.startswith("check file "):
        return "dev_review_file"

    if text.startswith("explain file ") or text.startswith("summarize file "):
        return "dev_explain_file"

    if text.startswith("view patch "):
        return "patch_view"

    if text.startswith("apply patch "):
        return "patch_apply"

    if text.startswith("deny patch "):
        return "patch_deny"


    if text in {"pending patches", "show patches", "show pending patches", "list patches"}:
        return "patch_pending"

    if text.startswith("view patch "):
        return "patch_view"

    if text.startswith("apply patch "):
        return "patch_apply"

    if text.startswith("deny patch "):
        return "patch_deny"

    prompt = f"""
Classify the user's message into exactly one command.

Allowed commands:
{", ".join(sorted(ALLOWED_COMMANDS))}

Rules:
- Return ONLY JSON.
- JSON format: {{"command":"dev_read"}}
- If the user asks to read/open/show a project file, use dev_read.
- If the user asks to search/find/where something is in the project, use dev_search.
- If the user asks a question about an ingested document, PDF, book, or manual, use doc_query.
- If the user asks to review/audit/check code, use dev_review_file.
- If the user asks to explain/summarize a source file, use dev_explain_file.
- If the user asks for system health, RAM, CPU, or disk, use system_status.
- If the user asks for GPU/VRAM/NVIDIA, use gpu_status.
- If the user asks for Docker/containers, use docker_status.
- If unsure, use chat.

User message:
{message}
""".strip()

    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            response = await client.post(
                "http://ollama:11434/api/chat",
                json={
                    "model": "llama3.1:8b",
                    "messages": [
                        {
                            "role": "system",
                            "content": "You are a strict command classifier. Return only valid JSON.",
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

        content = data.get("message", {}).get("content", "").strip()

        if content.startswith("```"):
            content = content.strip("`").strip()
            if content.startswith("json"):
                content = content[4:].strip()

        parsed = json.loads(content)
        command = parsed.get("command", fallback_command)

        if command in ALLOWED_COMMANDS:
            return command

        return fallback_command

    except Exception:
        return fallback_command
