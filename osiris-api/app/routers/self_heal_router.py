from typing import Any

from self_heal import propose_self_heal_patch


SELF_HEAL_COMMANDS = {
    "self_heal",
}



def is_self_heal_dry_run(message: str) -> bool:
    text = (message or "").lower().strip()

    dry_run_phrases = {
        "self heal dry run",
        "self-heal dry run",
        "self heal test",
        "self-heal test",
        "self heal check",
        "self-heal check",
        "test self heal",
        "test self-heal",
    }

    return (
        text in dry_run_phrases
        or text.startswith("self heal dry run ")
        or text.startswith("self-heal dry run ")
        or text.startswith("self heal test ")
        or text.startswith("self-heal test ")
        or text.startswith("self heal check ")
        or text.startswith("self-heal check ")
    )


def self_heal_dry_run_response(message: str) -> dict:
    return {
        "type": "tool_result",
        "command": "self_heal",
        "answer": (
            "Self-heal route check passed. Dry-run mode did not generate "
            "or store a patch."
        ),
        "data": {
            "status": "dry_run",
            "patch_created": False,
            "message": message,
        },
    }

async def handle_self_heal_command(command: str, message: str) -> dict[str, Any]:

    if is_self_heal_dry_run(message):
        return self_heal_dry_run_response(message)

    if command != "self_heal":
        return {
            "type": "tool_result",
            "command": command,
            "answer": f"Unknown self-heal command: {command}",
            "data": None,
        }

    lowered = message.lower()
    marker = " issue "

    if "self heal file " not in lowered or marker not in lowered:
        return {
            "type": "tool_result",
            "command": command,
            "answer": (
                "Use this format: self heal file "
                "osiris-api/app/file.py issue describe the problem"
            ),
            "data": None,
        }

    start = lowered.find("self heal file ") + len("self heal file ")
    split_at = lowered.find(marker)

    file_path = message[start:split_at].strip().strip('"').strip("'")
    issue = message[split_at + len(marker):].strip()

    result = await propose_self_heal_patch(
        file_path=file_path,
        issue=issue,
    )

    patch = result.get("patch", {})

    answer = (
        "Self-heal patch proposed and added to pending patches.\n\n"
        f"Patch ID: {patch.get('id')}\n"
        f"File: {patch.get('file_path')}\n"
        f"Reason: {patch.get('reason')}\n\n"
        "Review it before applying. Tiny detail, but important if we enjoy systems that still boot."
    )

    return {
        "type": "tool_result",
        "command": command,
        "answer": answer,
        "data": result,
    }
