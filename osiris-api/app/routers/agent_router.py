from typing import Any

from cognition import build_execution_plan
from cognition_executor import execute_plan
from reasoner import run_reasoning_loop


AGENT_COMMANDS = {
    "agent_loop",
    "cognition",
}


async def build_cognitive_plan(message: str) -> dict[str, Any]:
    plan = build_execution_plan(message)

    execution = await execute_plan(plan, message=message)

    summary = []

    for result in execution["results"]:
        summary.append(
            f'{result["step"]}: {result["output"]}'
        )

    return {
        "type": "cognitive_execution",
        "command": "cognition",
        "message": message,
        "answer": "Autonomous execution completed:\n\n" + "\n".join(summary),
        "data": {
            "steps": plan,
            "execution": execution,
        },
    }


async def handle_agent_command(command: str, message: str) -> dict[str, Any]:
    if command == "agent_loop":
        return await run_reasoning_loop(message, max_rounds=3)

    if command == "cognition":
        return await build_cognitive_plan(message)

    return {
        "type": "tool_result",
        "command": command,
        "answer": f"Unknown agent command: {command}",
        "data": None,
    }
