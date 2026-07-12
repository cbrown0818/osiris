from typing import Any

from host_agent_client import (
    get_host_summary,
    get_host_system_status,
    get_host_gpu_status,
    get_host_docker_status,
    get_host_security_status,
)

from system_monitor import get_full_system_snapshot


SYSTEM_COMMANDS = {
    "security_status",
    "host_summary",
    "system_status",
    "gpu_status",
    "docker_status",
    "system_snapshot",
}


def format_host_summary(data: dict[str, Any]) -> str:
    system = data.get("system", {})
    host = system.get("host", {})
    cpu = system.get("cpu", {})
    memory = system.get("memory", {})
    disk = system.get("disk", {})
    gpu = data.get("gpu", {})
    network = data.get("network", {})

    gpu_text = "GPU not detected."
    if gpu.get("available") and gpu.get("gpus"):
        g = gpu["gpus"][0]
        gpu_text = (
            f"{g.get('name')} | temp {g.get('temperature_c')}°C | "
            f"VRAM {g.get('memory_used_mib')}/{g.get('memory_total_mib')} MiB | "
            f"utilization {g.get('utilization_percent')}%"
        )

    return (
        f"Your tower **{host.get('hostname', 'Osiris')}** is running well.\n\n"
        f"CPU: {cpu.get('physical_cores')} physical cores / {cpu.get('logical_cores')} threads, "
        f"currently around {cpu.get('percent')}% usage.\n"
        f"RAM: {memory.get('used_gb')} GB used out of {memory.get('total_gb')} GB "
        f"({memory.get('available_gb')} GB available).\n"
        f"Disk: {disk.get('used_gb')} GB used out of {disk.get('total_gb')} GB "
        f"({disk.get('free_gb')} GB free).\n"
        f"GPU: {gpu_text}.\n"
        f"Main IPs: {', '.join(network.get('ip_addresses', [])[:4])}."
    )


async def handle_system_command(command: str) -> dict[str, Any]:
    if command == "system_snapshot":
        data = await get_full_system_snapshot()
        answer = (
            "Full system snapshot completed. "
            f"Summary: {data.get('summary', {}).get('status')}. "
            f"System: {data.get('system', {}).get('status')}. "
            f"GPU: {data.get('gpu', {}).get('status')}. "
            f"Docker: {data.get('docker', {}).get('status')}. "
            f"Security: {data.get('security', {}).get('status')}."
        )
        return {"type": "tool_result", "command": command, "answer": answer, "data": data}

    if command == "security_status":
        data = await get_host_security_status()
        grade = data.get("grade", "Unknown")
        issues = data.get("issues", [])
        warnings = data.get("warnings", [])
        passed = data.get("passed", [])

        answer = f"Security grade: **{grade}**\n\n"
        answer += "Issues: none detected.\n\n" if not issues else "Issues:\n" + "\n".join(f"- {x}" for x in issues) + "\n\n"
        answer += "Warnings: none.\n\n" if not warnings else "Warnings:\n" + "\n".join(f"- {x}" for x in warnings) + "\n\n"
        answer += "Passed checks:\n" + "\n".join(f"- {x}" for x in passed[:10])

        return {"type": "tool_result", "command": command, "answer": answer, "data": data}

    if command == "host_summary":
        data = await get_host_summary()
        return {"type": "tool_result", "command": command, "answer": format_host_summary(data), "data": data}

    if command == "system_status":
        data = await get_host_system_status()
        memory = data.get("memory", {})
        cpu = data.get("cpu", {})
        disk = data.get("disk", {})
        answer = (
            f"System status: CPU is at {cpu.get('percent')}%. "
            f"RAM is {memory.get('used_gb')} GB used out of {memory.get('total_gb')} GB, "
            f"with {memory.get('available_gb')} GB available. "
            f"Disk has {disk.get('free_gb')} GB free."
        )
        return {"type": "tool_result", "command": command, "answer": answer, "data": data}

    if command == "gpu_status":
        data = await get_host_gpu_status()
        if data.get("available") and data.get("gpus"):
            g = data["gpus"][0]
            answer = (
                f"GPU: {g.get('name')}. Driver {g.get('driver_version')}. "
                f"Temperature {g.get('temperature_c')}°C. "
                f"VRAM {g.get('memory_used_mib')}/{g.get('memory_total_mib')} MiB. "
                f"Utilization {g.get('utilization_percent')}%."
            )
        else:
            answer = "I could not detect an available NVIDIA GPU from the Host Agent."
        return {"type": "tool_result", "command": command, "answer": answer, "data": data}

    if command == "docker_status":
        data = await get_host_docker_status()
        return {"type": "tool_result", "command": command, "answer": "Docker status retrieved.", "data": data}

    return {
        "type": "tool_result",
        "command": command,
        "answer": f"Unknown system command: {command}",
        "data": None,
    }
