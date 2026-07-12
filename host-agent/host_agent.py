import shutil
import socket
import subprocess
from datetime import datetime
from typing import Any

import psutil
from fastapi import FastAPI


app = FastAPI(
    title="Osiris Host Agent",
    description="Fedora host-side system agent for Osiris.",
    version="1.0.0",
)


def run_command(command: list[str], timeout: int = 10) -> dict[str, Any]:
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )

        return {
            "ok": result.returncode == 0,
            "returncode": result.returncode,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
        }

    except FileNotFoundError:
        return {
            "ok": False,
            "returncode": -1,
            "stdout": "",
            "stderr": f"Command not found: {command[0]}",
        }

    except Exception as exc:
        return {
            "ok": False,
            "returncode": -1,
            "stdout": "",
            "stderr": str(exc),
        }


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "Osiris Host Agent",
        "hostname": socket.gethostname(),
        "time": datetime.now().isoformat(),
    }


@app.get("/system/status")
def system_status():
    memory = psutil.virtual_memory()
    swap = psutil.swap_memory()
    disk = shutil.disk_usage("/")
    boot_time = datetime.fromtimestamp(psutil.boot_time())

    return {
        "host": {
            "hostname": socket.gethostname(),
            "time": datetime.now().isoformat(),
            "boot_time": boot_time.isoformat(),
            "uptime_seconds": int(datetime.now().timestamp() - psutil.boot_time()),
        },
        "cpu": {
            "physical_cores": psutil.cpu_count(logical=False),
            "logical_cores": psutil.cpu_count(logical=True),
            "percent": psutil.cpu_percent(interval=0.5),
            "load_average": psutil.getloadavg() if hasattr(psutil, "getloadavg") else None,
        },
        "memory": {
            "total_gb": round(memory.total / 1024**3, 2),
            "available_gb": round(memory.available / 1024**3, 2),
            "used_gb": round(memory.used / 1024**3, 2),
            "percent": memory.percent,
        },
        "swap": {
            "total_gb": round(swap.total / 1024**3, 2),
            "used_gb": round(swap.used / 1024**3, 2),
            "percent": swap.percent,
        },
        "disk": {
            "path": "/",
            "total_gb": round(disk.total / 1024**3, 2),
            "used_gb": round(disk.used / 1024**3, 2),
            "free_gb": round(disk.free / 1024**3, 2),
            "percent": round((disk.used / disk.total) * 100, 2),
        }
    }


@app.get("/docker/status")
def docker_status():
    docker = run_command([
        "docker",
        "ps",
        "--format",
        "table {{.Names}}\\t{{.Status}}\\t{{.Ports}}"
    ])

    compose = run_command(
        ["docker", "compose", "ps"],
        timeout=15
    )

    return {
        "docker_ps": docker,
        "docker_compose_ps": compose,
    }


@app.get("/gpu/status")
def gpu_status():
    nvidia = run_command([
        "nvidia-smi",
        "--query-gpu=name,driver_version,temperature.gpu,utilization.gpu,memory.used,memory.total,power.draw",
        "--format=csv,noheader,nounits"
    ])

    if not nvidia["ok"]:
        return {
            "available": False,
            "error": nvidia["stderr"],
        }

    gpus = []
    for line in nvidia["stdout"].splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) >= 7:
            gpus.append({
                "name": parts[0],
                "driver_version": parts[1],
                "temperature_c": parts[2],
                "utilization_percent": parts[3],
                "memory_used_mib": parts[4],
                "memory_total_mib": parts[5],
                "power_draw_w": parts[6],
            })

    return {
        "available": True,
        "gpus": gpus,
    }


@app.get("/network/status")
def network_status():
    hostname = socket.gethostname()
    ips = run_command(["hostname", "-I"])

    return {
        "hostname": hostname,
        "ip_addresses": ips["stdout"].split() if ips["ok"] else [],
        "raw": ips,
    }


@app.get("/summary")
def summary():
    return {
        "health": health(),
        "system": system_status(),
        "gpu": gpu_status(),
        "network": network_status(),
    }


# -------------------------------------------------------------------
# Osiris Host Security Status
# -------------------------------------------------------------------

SENSITIVE_PORTS = [
    "81", "8000", "8088", "1883", "5055",
    "6333", "6334", "11434", "5432", "3001"
]


def run_command(command: list[str], timeout: int = 15) -> dict:
    import subprocess

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        return {
            "ok": result.returncode == 0,
            "returncode": result.returncode,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
        }
    except Exception as exc:
        return {
            "ok": False,
            "returncode": -1,
            "stdout": "",
            "stderr": str(exc),
        }


@app.get("/security/status")
def security_status():
    firewall = run_command(["firewall-cmd", "--list-all"])

    listeners = run_command([
        "bash",
        "-lc",
        "ss -tulpn | grep -E ':80|:443|:81|:8000|:8088|:1883|:5055|:6333|:6334|:11434|:5432|:3001' || true"
    ])

    docker_ports = run_command([
        "bash",
        "-lc",
        "docker ps --format 'table {{.Names}}\\t{{.Status}}\\t{{.Ports}}' || true"
    ])

    issues = []
    warnings = []
    passed = []

    listener_text = listeners.get("stdout", "")

    allowed_public = [":80", ":443"]

    for port in SENSITIVE_PORTS:
        for line in listener_text.splitlines():
            if f":{port}" in line:
                if "127.0.0.1" in line:
                    passed.append(f"Port {port} is localhost-only.")
                elif port == "5055":
                    if "0.0.0.0:5055" in line or "[::]:5055" in line:
                        warnings.append("Host Agent 5055 is listening on all interfaces; firewall reject rule should protect it.")
                    elif "172.17.0.1:5055" in line:
                        passed.append("Host Agent 5055 is bound to Docker gateway only.")
                    else:
                        warnings.append(f"Host Agent 5055 is listening on a non-localhost interface: {line}")
                else:
                    issues.append(f"Sensitive port {port} appears exposed: {line}")

    if ":80" in listener_text:
        passed.append("HTTP port 80 is listening for public web.")
    if ":443" in listener_text:
        passed.append("HTTPS port 443 is listening for public web.")

    firewall_text = firewall.get("stdout", "")
    if "port port=\"5055\" protocol=\"tcp\" reject" in firewall_text:
        passed.append("Firewall reject rule for Host Agent 5055 is active.")
    else:
        warnings.append("Firewall reject rule for Host Agent 5055 was not detected.")

    if "services: http https ssh" in firewall_text or ("http" in firewall_text and "https" in firewall_text and "ssh" in firewall_text):
        passed.append("Firewall services are limited to http, https, and ssh.")
    else:
        warnings.append("Firewall services should be reviewed.")

    if issues:
        grade = "Needs Attention"
    elif warnings:
        grade = "Good with Warnings"
    else:
        grade = "Strong"

    return {
        "status": "ok",
        "grade": grade,
        "issues": issues,
        "warnings": warnings,
        "passed": passed,
        "raw": {
            "firewall": firewall,
            "listeners": listeners,
            "docker_ports": docker_ports,
        },
    }
