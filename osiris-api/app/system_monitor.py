from typing import Any

from host_agent_client import (
    get_host_summary,
    get_host_system_status,
    get_host_gpu_status,
    get_host_docker_status,
    get_host_security_status,
)


async def safe_call(name: str, func) -> dict[str, Any]:
    try:
        return {
            "name": name,
            "status": "ok",
            "data": await func(),
        }
    except Exception as exc:
        return {
            "name": name,
            "status": "error",
            "error_type": type(exc).__name__,
            "error": str(exc),
        }


async def get_full_system_snapshot() -> dict[str, Any]:
    return {
        "summary": await safe_call("summary", get_host_summary),
        "system": await safe_call("system", get_host_system_status),
        "gpu": await safe_call("gpu", get_host_gpu_status),
        "docker": await safe_call("docker", get_host_docker_status),
        "security": await safe_call("security", get_host_security_status),
    }
