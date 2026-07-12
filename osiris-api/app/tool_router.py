import subprocess
from typing import Any

from permissions import check_tool
from action_logger import log_action
from approvals import create_approval


class ToolRouterError(Exception):
    pass


def run_command(command: list[str], timeout: int = 20) -> dict[str, Any]:
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )

        return {
            "returncode": result.returncode,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
        }

    except Exception as exc:
        return {
            "returncode": -1,
            "stdout": "",
            "stderr": str(exc),
        }


def tool_system_status(params: dict[str, Any]) -> dict[str, Any]:
    uptime = run_command(["uptime"])
    memory = run_command(["free", "-h"])
    disk = run_command(["df", "-h", "/"])

    return {
        "uptime": uptime,
        "memory": memory,
        "disk": disk,
    }


def tool_docker_status(params: dict[str, Any]) -> dict[str, Any]:
    # This runs inside osiris-api container, so Docker CLI may not exist here.
    # For now this is a placeholder until we add a host-side agent.
    return {
        "status": "placeholder",
        "message": "Docker status requires host-agent support. API container cannot directly inspect host Docker yet."
    }


def tool_robot_status(params: dict[str, Any]) -> dict[str, Any]:
    device_id = params.get("device_id", "pi_robot_1")

    return {
        "device_id": device_id,
        "status": "placeholder",
        "message": "Robot status tool is wired, but MQTT device agent is not connected yet."
    }


def tool_robot_emergency_stop(params: dict[str, Any]) -> dict[str, Any]:
    device_id = params.get("device_id", "pi_robot_1")

    return {
        "device_id": device_id,
        "status": "safety_placeholder",
        "message": "Emergency stop tool is wired. MQTT stop command will be added in the next device-core phase."
    }


TOOL_MAP = {
    "status_checks": tool_system_status,
    "docker_status": tool_docker_status,
    "robot_status": tool_robot_status,
    "robot_emergency_stop": tool_robot_emergency_stop,
}


def run_tool(tool_name: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    params = params or {}

    permission = check_tool(tool_name)

    if not permission.get("allowed"):
        log_action({
            "tool": tool_name,
            "params": params,
            "allowed": False,
            "approval_required": False,
            "result": "blocked",
            "reason": permission.get("reason"),
        })

        return {
            "status": "blocked",
            "permission": permission,
        }

    if permission.get("approval_required"):
        approval = create_approval(
            tool_name=tool_name,
            params=params,
            permission=permission,
            target=params.get("device_id") or params.get("target"),
            action=params.get("action"),
        )

        log_action({
            "tool": tool_name,
            "params": params,
            "allowed": True,
            "approval_required": True,
            "result": "approval_created",
            "approval_id": str(approval["id"]),
            "reason": permission.get("reason"),
        })

        return {
            "status": "approval_required",
            "approval_id": str(approval["id"]),
            "approval": approval,
            "permission": permission,
            "message": f"{tool_name} requires approval before running."
        }

    if tool_name not in TOOL_MAP:
        log_action({
            "tool": tool_name,
            "params": params,
            "allowed": True,
            "approval_required": False,
            "result": "missing_tool_handler",
        })

        return {
            "status": "error",
            "message": f"No handler exists for tool: {tool_name}"
        }

    result = TOOL_MAP[tool_name](params)

    log_action({
        "tool": tool_name,
        "params": params,
        "allowed": True,
        "approval_required": False,
        "result": "executed",
        "output": result,
    })

    return {
        "status": "executed",
        "tool": tool_name,
        "permission": permission,
        "result": result,
    }
