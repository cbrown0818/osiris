from __future__ import annotations

from typing import Any

from osiris_core.runtime import core


AGENT_COMMANDS = {
    "agent_loop",
    "cognition",
}


def _failure_response(
    command: str,
    result: dict[str, Any],
) -> dict[str, Any]:
    error = result.get("error") or {}
    authorization = (
        result.get("authorization")
        or {}
    )

    error_type = error.get(
        "type",
        "CapabilityError",
    )

    message = error.get(
        "message",
        "The requested capability could not be executed.",
    )

    approval_id = authorization.get(
        "approval_id"
    )

    response_type = (
        "approval_required"
        if error_type == "ApprovalRequired"
        else "tool_result"
    )

    if (
        response_type == "approval_required"
        and approval_id
    ):
        message = (
            f"{message}\n\n"
            f"Approval ID: {approval_id}\n"
            "Open Approvals to review and execute "
            "this exact request."
        )

    return {
        "type": response_type,
        "command": command,
        "answer": message,
        "data": {
            "approval_id": approval_id,
            "authorization": authorization,
            "capability_result": result,
        },
    }


async def build_cognitive_plan(
    message: str,
) -> dict[str, Any]:
    result = await core.adapters.execute(
        "intelligence.reasoning",
        {
            "goal": message,
        },
    )

    result_data = result.as_dict()

    if not result.success:
        return _failure_response(
            "cognition",
            result_data,
        )

    planning = result.result
    plan = planning.get("plan", [])

    if plan:
        plan_text = "\n".join(
            f"- {step}"
            for step in plan
        )
    else:
        plan_text = "- No steps proposed."

    return {
        "type": "cognitive_plan",
        "command": "cognition",
        "message": message,
        "answer": (
            "Planning completed. No actions were executed.\n\n"
            "Proposed plan:\n"
            f"{plan_text}"
        ),
        "data": {
            "planning": planning,
            "steps": plan,
            "execution": None,
        },
    }


async def handle_agent_command(
    command: str,
    message: str,
) -> dict[str, Any]:
    if command == "cognition":
        return await build_cognitive_plan(message)

    if command == "agent_loop":
        result = await core.adapters.execute(
            "intelligence.agent_execution",
            {
                "goal": message,
            },
        )

        return _failure_response(
            command,
            result.as_dict(),
        )

    return {
        "type": "tool_result",
        "command": command,
        "answer": f"Unknown agent command: {command}",
        "data": None,
    }
