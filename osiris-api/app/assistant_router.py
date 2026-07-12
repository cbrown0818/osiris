from typing import Any

from command_detector import detect_command
from intent_classifier import classify_intent_with_ai
from memory import save_memory
from routers.command_registry import can_dispatch_command, dispatch_command


def chat_response() -> dict[str, Any]:
    return {
        "type": "chat",
        "command": "chat",
        "answer": None,
        "data": None,
    }


async def save_interaction(command: str, message: str) -> None:
    try:
        await save_memory(
            memory_type="interaction",
            title=f"Command: {command}",
            content=message,
            metadata={
                "command": command
            }
        )
    except Exception as e:
        print(f"[Memory Error] {str(e)}")


async def handle_assistant_command(message: str) -> dict[str, Any]:
    clean_message = (message or "").strip()

    if not clean_message:
        return chat_response()

    detected_command = detect_command(clean_message)

    if detected_command != "chat" and can_dispatch_command(detected_command):
        command = detected_command
    else:
        command = await classify_intent_with_ai(
            clean_message,
            fallback_command=detected_command,
        )

    await save_interaction(command, clean_message)

    if can_dispatch_command(command):
        return await dispatch_command(command, clean_message)

    return chat_response()
