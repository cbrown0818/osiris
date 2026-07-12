import json
from pathlib import Path
from typing import Any

from permissions import check_tool
from action_logger import log_action
from mqtt_bridge import publish_command
from approvals import create_approval

APP_DIR = Path("/app")
DEVICES_FILE = APP_DIR / "config" / "devices.json"


class DeviceCoreError(Exception):
    pass


def load_devices() -> dict[str, Any]:
    if not DEVICES_FILE.exists():
        raise FileNotFoundError(f"Missing devices file: {DEVICES_FILE}")

    with DEVICES_FILE.open("r", encoding="utf-8") as f:
        return json.load(f)


def get_device(device_id: str) -> dict[str, Any]:
    data = load_devices()
    devices = data.get("devices", {})

    if device_id not in devices:
        raise DeviceCoreError(f"Unknown device: {device_id}")

    device = devices[device_id]

    if not device.get("enabled", False):
        raise DeviceCoreError(f"Device is disabled: {device_id}")

    return device


def device_allows_capability(device: dict[str, Any], capability: str) -> bool:
    return capability in device.get("capabilities", [])


def send_device_command(
    device_id: str,
    tool_name: str,
    capability: str,
    action: str,
    params: dict[str, Any] | None = None,
    force_approved: bool = False
) -> dict[str, Any]:
    params = params or {}

    permission = check_tool(tool_name)

    if force_approved and permission.get("allowed"):
        permission["approval_required"] = False
        permission["reason"] = "Previously approved by Master."

    if not permission.get("allowed"):
        log_action({
            "tool": tool_name,
            "device_id": device_id,
            "capability": capability,
            "action": action,
            "params": params,
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
            params={
                "device_id": device_id,
                "capability": capability,
                "action": action,
                "params": params,
            },
            permission=permission,
            target=device_id,
            action=action,
        )

        log_action({
            "tool": tool_name,
            "device_id": device_id,
            "capability": capability,
            "action": action,
            "params": params,
            "result": "approval_created",
            "approval_id": str(approval["id"]),
            "reason": permission.get("reason"),
        })

        return {
            "status": "approval_required",
            "approval_id": str(approval["id"]),
            "approval": approval,
            "permission": permission,
            "message": f"{tool_name} requires approval before sending command."
        }

    device = get_device(device_id)

    if not device_allows_capability(device, capability):
        raise DeviceCoreError(
            f"Device {device_id} does not allow capability {capability}"
        )

    communication = device.get("communication", {})
    method = communication.get("method")

    if method != "mqtt":
        raise DeviceCoreError(f"Unsupported communication method: {method}")

    topic = communication.get("command_topic")

    if not topic:
        raise DeviceCoreError(f"Missing command topic for device: {device_id}")

    payload = {
        "device_id": device_id,
        "capability": capability,
        "action": action,
        "params": params,
        "issued_by": "Master"
    }

    result = publish_command(topic, payload)

    log_action({
        "tool": tool_name,
        "device_id": device_id,
        "capability": capability,
        "action": action,
        "params": params,
        "result": "mqtt_published",
        "mqtt": result,
    })

    return {
        "status": "sent",
        "device": {
            "id": device_id,
            "name": device.get("name"),
            "type": device.get("type"),
            "platform": device.get("platform")
        },
        "permission": permission,
        "mqtt": result,
    }


def emergency_stop(device_id: str) -> dict[str, Any]:
    return send_device_command(
        device_id=device_id,
        tool_name="robot_emergency_stop",
        capability="robot.emergency_stop",
        action="stop_all",
        params={
            "priority": "critical"
        }
    )
