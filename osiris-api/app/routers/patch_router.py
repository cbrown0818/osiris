from typing import Any
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
    if command == "patch_generate_ai":
        lowered = message.lower()

        trigger = None
        for phrase in ["generate patch for ", "create patch for ", "make patch for ", "ai patch for "]:
            if phrase in lowered:
                trigger = phrase
                break

        if not trigger:
            return {
                "type": "tool_result",
                "command": command,
                "answer": "Tell me the file and change. Example: generate patch for scripts/patch-test.txt to change it to say hello",
                "data": None,
            }

        after = message[lowered.find(trigger) + len(trigger):].strip()

        split_words = [" to ", " that ", " so "]
        file_path = None
        instruction = None

        for word in split_words:
            if word in after:
                parts = after.split(word, 1)
                file_path = parts[0].strip()
                instruction = parts[1].strip()
                break

        if not file_path or not instruction:
            return {
                "type": "tool_result",
                "command": command,
                "answer": (
                    "I need both a file path and an instruction. Example:\n"
                    "generate patch for scripts/patch-test.txt to change it to say hello from Osiris"
                ),
                "data": None,
            }

        result = await generate_patch_with_ai(
            file_path=file_path,
            instruction=instruction,
            model="qwen2.5-coder:7b",
        )

        patch = result.get("patch", {})
        answer = (
            "AI patch generated and added to pending patches.\n\n"
            f"Patch ID: {patch.get('id')}\n"
            f"File: {patch.get('file_path')}\n"
            f"Reason: {patch.get('reason')}\n\n"
            f"{patch.get('diff')}\n\n"
            "Review it, then apply with:\n"
            f"apply patch {patch.get('id')}"
        )

        return {
            "type": "tool_result",
            "command": command,
            "answer": answer,
            "data": result,
        }


    if command == "patch_backups":
        backups = list_patch_backups()

        if not backups:
            answer = "No patch backups were found."
        else:
            lines = []
            for backup in backups[:25]:
                lines.append(
                    f"{backup['backup_path']} -> {backup['original_path']} | {backup['size_bytes']} bytes"
                )
            answer = "Patch backups:\n\n" + "\n".join(lines)

        return {
            "type": "tool_result",
            "command": command,
            "answer": answer,
            "data": {
                "count": len(backups),
                "backups": backups,
            },
        }

    if command == "patch_restore_request":
        lowered = message.lower()

        trigger = None
        for phrase in ["restore backup ", "rollback backup "]:
            if phrase in lowered:
                trigger = phrase
                break

        if not trigger:
            return {
                "type": "tool_result",
                "command": command,
                "answer": "Tell me the backup path. Example: restore backup scripts/file.py.backup.patch.2026-...",
                "data": None,
            }

        start = lowered.find(trigger) + len(trigger)
        backup_path = message[start:].strip().strip('"').strip("'")

        if not backup_path:
            return {
                "type": "tool_result",
                "command": command,
                "answer": "I need the backup path to restore.",
                "data": None,
            }

        approval = create_approval(
            tool_name="patch_rollback",
            target=backup_path,
            action="restore_patch_backup",
            params={
                "backup_path": backup_path,
            },
            permission={
                "allowed": True,
                "approval_required": True,
                "risk": "high",
                "category": "development",
                "reason": "Restoring a patch backup modifies project files and requires approval.",
            },
        )

        answer = (
            "Rollback restore requires approval before it is applied.\n\n"
            f"Approval ID: {approval['id']}\n"
            f"Backup: {backup_path}\n\n"
            "Open Approvals or approve it with:\n"
            f"approve approval {approval['id']}"
        )

        return {
            "type": "tool_result",
            "command": command,
            "answer": answer,
            "data": {
                "approval": approval,
            },
        }

    if command == "patch_pending":
        patches = list_pending_patches(limit=25)

        if not patches:
            answer = "There are no pending patches."
        else:
            lines = []
            for patch in patches:
                lines.append(
                    f"{patch['id']} | {patch['file_path']} | {patch.get('reason') or 'no reason'}"
                )
            answer = "Pending patches:\n\n" + "\n".join(lines)

        return {
            "type": "tool_result",
            "command": command,
            "answer": answer,
            "data": {
                "count": len(patches),
                "patches": patches,
            },
        }

    if command in ["patch_view", "patch_apply", "patch_deny"]:
        match = re.search(
            r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
            message.lower()
        )

        if not match:
            return {
                "type": "tool_result",
                "command": command,
                "answer": "I need a patch ID. Example: apply patch 28507717-58a8-4a6e-b56a-355ab55b87b3",
                "data": None,
            }

        patch_id = match.group(0)

        if command == "patch_view":
            patch = get_patch(patch_id)
            if not patch:
                answer = f"Patch not found: {patch_id}"
            else:
                answer = (
                    f"Patch: {patch_id}\n"
                    f"File: {patch.get('file_path')}\n"
                    f"Status: {patch.get('status')}\n"
                    f"Reason: {patch.get('reason')}\n\n"
                    f"{patch.get('diff')}"
                )

            return {
                "type": "tool_result",
                "command": command,
                "answer": answer,
                "data": patch,
            }

        if command == "patch_apply":
            result = apply_patch(patch_id)
            patch_result = result.get("result", {})

            try:
                await save_memory(
                    memory_type="patch_outcome",
                    title=f"Patch applied: {patch_id}",
                    content=(
                        f"Applied patch {patch_id} to "
                        f"{patch_result.get('file_path')}. "
                        f"Backup created at {patch_result.get('backup_path')}."
                    ),
                    metadata={
                        "patch_id": patch_id,
                        "status": "applied",
                        "file_path": patch_result.get("file_path"),
                        "backup_path": patch_result.get("backup_path"),
                    },
                )
            except Exception as exc:
                print(f"[Memory Error] {type(exc).__name__}: {str(exc)}")

            answer = (
                f"Patch applied successfully.\n"
                f"File: {patch_result.get('file_path')}\n"
                f"Backup: {patch_result.get('backup_path')}"
            )

            return {
                "type": "tool_result",
                "command": command,
                "answer": answer,
                "data": result,
            }

        if command == "patch_deny":
            result = deny_patch(patch_id)

            try:
                await save_memory(
                    memory_type="patch_outcome",
                    title=f"Patch denied: {patch_id}",
                    content=f"Denied patch {patch_id}.",
                    metadata={
                        "patch_id": patch_id,
                        "status": "denied",
                    },
                )
            except Exception as exc:
                print(f"[Memory Error] {type(exc).__name__}: {str(exc)}")

            answer = f"Patch denied: {patch_id}"

            return {
                "type": "tool_result",
                "command": command,
                "answer": answer,
                "data": result,
            }


    return {
        "type": "tool_result",
        "command": command,
        "answer": f"Patch command was not handled: {command}",
        "data": None,
    }
