import json
from pathlib import Path
from typing import Any


APP_DIR = Path("/app")
CONFIG_DIR = APP_DIR / "config"
PERMISSIONS_FILE = CONFIG_DIR / "permissions.json"


class OsirisPermissionError(Exception):
    pass


def load_permissions() -> dict[str, Any]:
    if not PERMISSIONS_FILE.exists():
        raise FileNotFoundError(f"Missing permissions file: {PERMISSIONS_FILE}")

    with PERMISSIONS_FILE.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_permissions(data: dict[str, Any]) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    with PERMISSIONS_FILE.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def check_tool(tool_name: str) -> dict[str, Any]:
    data = load_permissions()
    tools = data.get("tools", {})

    if tool_name not in tools:
        return {
            "allowed": False,
            "approval_required": False,
            "reason": f"Unknown tool: {tool_name}"
        }

    tool = tools[tool_name]

    if tool.get("always_allowed"):
        return {
            "allowed": True,
            "approval_required": False,
            "risk": tool.get("risk", "unknown"),
            "category": tool.get("category", "unknown"),
            "reason": "Tool is always allowed."
        }

    if not tool.get("enabled", False):
        return {
            "allowed": False,
            "approval_required": False,
            "risk": tool.get("risk", "unknown"),
            "category": tool.get("category", "unknown"),
            "reason": f"{tool_name} is disabled."
        }

    mode = data.get("mode", "normal")
    risk = tool.get("risk", "unknown")
    category = tool.get("category", "unknown")

    if mode == "safe" and risk not in ["low", "safety"]:
        return {
            "allowed": False,
            "approval_required": False,
            "risk": risk,
            "category": category,
            "reason": f"{tool_name} is blocked in Safe Mode."
        }

    if category == "pentest":
        pentest = data.get("pentest_mode", {})

        if not pentest.get("enabled", False):
            return {
                "allowed": False,
                "approval_required": False,
                "risk": risk,
                "category": category,
                "reason": "Pentest Mode is disabled."
            }

        if pentest.get("scope_required", True):
            scope_file = Path(pentest.get("scope_file", ""))

            if not scope_file.exists():
                return {
                    "allowed": False,
                    "approval_required": False,
                    "risk": risk,
                    "category": category,
                    "reason": "Pentest scope file is missing."
                }

    return {
        "allowed": True,
        "approval_required": tool.get("approval_required", True),
        "risk": risk,
        "category": category,
        "reason": "Allowed by current permission settings."
    }


def set_mode(mode: str) -> dict[str, Any]:
    allowed_modes = ["safe", "normal", "pentest", "admin"]

    if mode not in allowed_modes:
        raise OsirisPermissionError(f"Invalid mode. Use one of: {allowed_modes}")

    data = load_permissions()
    data["mode"] = mode

    if mode == "pentest":
        data.setdefault("pentest_mode", {})
        data["pentest_mode"]["enabled"] = True

    if mode in ["safe", "normal"]:
        data.setdefault("pentest_mode", {})
        data["pentest_mode"]["enabled"] = False

    save_permissions(data)
    return data


def update_tool(
    tool_name: str,
    enabled: bool | None = None,
    approval_required: bool | None = None
) -> dict[str, Any]:
    data = load_permissions()

    if tool_name not in data.get("tools", {}):
        raise OsirisPermissionError(f"Unknown tool: {tool_name}")

    if enabled is not None:
        data["tools"][tool_name]["enabled"] = enabled

    if approval_required is not None:
        data["tools"][tool_name]["approval_required"] = approval_required

    save_permissions(data)
    return data["tools"][tool_name]
