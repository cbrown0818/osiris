from typing import Any, Awaitable, Callable

from routers.agent_router import AGENT_COMMANDS, handle_agent_command
from routers.dev_review_router import DEV_REVIEW_COMMANDS, handle_dev_review_command
from routers.dev_router import DEV_COMMANDS, handle_dev_command
from routers.document_router import handle_document_query
from routers.patch_router import PATCH_COMMANDS, handle_patch_command
from routers.self_heal_router import SELF_HEAL_COMMANDS, handle_self_heal_command
from routers.system_router import SYSTEM_COMMANDS, handle_system_command


CommandHandler = Callable[[str, str], Awaitable[dict[str, Any]]]


async def _dispatch_system(command: str, message: str) -> dict[str, Any]:
    return await handle_system_command(command)


async def _dispatch_dev(command: str, message: str) -> dict[str, Any]:
    return await handle_dev_command(command, message)


async def _dispatch_document(command: str, message: str) -> dict[str, Any]:
    return await handle_document_query(message)


async def _dispatch_patch(command: str, message: str) -> dict[str, Any]:
    return await handle_patch_command(command, message)


async def _dispatch_dev_review(command: str, message: str) -> dict[str, Any]:
    return await handle_dev_review_command(command, message)


async def _dispatch_agent(command: str, message: str) -> dict[str, Any]:
    return await handle_agent_command(command, message)


async def _dispatch_self_heal(command: str, message: str) -> dict[str, Any]:
    return await handle_self_heal_command(command, message)


COMMAND_REGISTRY: dict[str, CommandHandler] = {}


for command in SYSTEM_COMMANDS:
    COMMAND_REGISTRY[command] = _dispatch_system

for command in DEV_COMMANDS:
    COMMAND_REGISTRY[command] = _dispatch_dev

for command in PATCH_COMMANDS:
    COMMAND_REGISTRY[command] = _dispatch_patch

for command in DEV_REVIEW_COMMANDS:
    COMMAND_REGISTRY[command] = _dispatch_dev_review

for command in AGENT_COMMANDS:
    COMMAND_REGISTRY[command] = _dispatch_agent

for command in SELF_HEAL_COMMANDS:
    COMMAND_REGISTRY[command] = _dispatch_self_heal


COMMAND_REGISTRY["doc_query"] = _dispatch_document


def can_dispatch_command(command: str) -> bool:
    return command in COMMAND_REGISTRY


async def dispatch_command(command: str, message: str) -> dict[str, Any]:
    handler = COMMAND_REGISTRY.get(command)

    if handler is None:
        return {
            "type": "chat",
            "command": "chat",
            "answer": None,
            "data": None,
        }

    return await handler(command, message)
