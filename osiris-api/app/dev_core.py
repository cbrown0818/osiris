from pathlib import Path
from typing import Any


PROJECT_ROOT = Path("/workspace").resolve()

ALLOWED_EXTENSIONS = {
    ".py", ".html", ".css", ".js", ".json", ".yml", ".yaml", ".md", ".txt",
    ".conf", ".service", ".sh", ".env.example"
}

BLOCKED_DIRS = {
    ".git",
    "__pycache__",
    ".venv",
    "node_modules",
    "postgres/data",
    "qdrant/storage",
    "ollama/data/models",
    "proxy/data",
    "proxy/letsencrypt",
    "monitoring/uptime-kuma",
    "backups",
}

BLOCKED_FILES = {
    ".env",
    "keys.json",
    "id_ed25519",
    "id_rsa",
}


class DevCoreError(Exception):
    pass


def safe_project_path(relative_path: str) -> Path:
    relative_path = relative_path.strip().lstrip("/")

    if not relative_path:
        return PROJECT_ROOT

    path = (PROJECT_ROOT / relative_path).resolve()

    if not str(path).startswith(str(PROJECT_ROOT)):
        raise DevCoreError("Path escapes project root.")

    return path


def is_blocked_path(path: Path) -> bool:
    rel = str(path.relative_to(PROJECT_ROOT))
    parts = set(path.relative_to(PROJECT_ROOT).parts)

    blocked_names_anywhere = {
        ".git",
        "__pycache__",
        ".venv",
        "node_modules",
        "logs",
        "cache",
    }

    if parts.intersection(blocked_names_anywhere):
        return True

    for blocked in BLOCKED_DIRS:
        if rel == blocked or rel.startswith(blocked + "/"):
            return True

    if path.name in BLOCKED_FILES:
        return True

    if ".backup." in path.name or path.name.endswith(".bak"):
        return True

    return False


def is_allowed_file(path: Path) -> bool:
    if is_blocked_path(path):
        return False

    if path.name in BLOCKED_FILES:
        return False

    if path.suffix in ALLOWED_EXTENSIONS:
        return True

    # Allow Dockerfile and extensionless common project files
    if path.name in {"Dockerfile", "README", "LICENSE"}:
        return True

    return False


def list_tree(max_depth: int = 4) -> dict[str, Any]:
    max_depth = max(1, min(max_depth, 8))
    items = []

    for path in sorted(PROJECT_ROOT.rglob("*")):
        try:
            rel_path = path.relative_to(PROJECT_ROOT)
        except ValueError:
            continue

        depth = len(rel_path.parts)

        if depth > max_depth:
            continue

        if is_blocked_path(path):
            if path.is_dir():
                items.append({
                    "path": str(rel_path),
                    "type": "directory",
                    "blocked": True,
                    "reason": "blocked directory"
                })
            continue

        items.append({
            "path": str(rel_path),
            "type": "directory" if path.is_dir() else "file",
            "size_bytes": path.stat().st_size if path.is_file() else None,
        })

    return {
        "project_root": str(PROJECT_ROOT),
        "max_depth": max_depth,
        "count": len(items),
        "items": items,
    }


def read_file(relative_path: str, max_bytes: int = 120_000) -> dict[str, Any]:
    path = safe_project_path(relative_path)

    if not path.exists():
        raise DevCoreError(f"File does not exist: {relative_path}")

    if not path.is_file():
        raise DevCoreError(f"Path is not a file: {relative_path}")

    if not is_allowed_file(path):
        raise DevCoreError(f"File is blocked or unsupported: {relative_path}")

    size = path.stat().st_size
    max_bytes = max(1_000, min(max_bytes, 500_000))

    content = path.read_text(encoding="utf-8", errors="replace")

    truncated = False
    if len(content.encode("utf-8")) > max_bytes:
        content = content.encode("utf-8")[:max_bytes].decode("utf-8", errors="replace")
        truncated = True

    return {
        "path": str(path.relative_to(PROJECT_ROOT)),
        "size_bytes": size,
        "truncated": truncated,
        "content": content,
    }


def search_project(query: str, max_results: int = 50) -> dict[str, Any]:
    query = query.strip()
    if not query:
        raise DevCoreError("Search query cannot be empty.")

    max_results = max(1, min(max_results, 200))
    query_lower = query.lower()
    results = []

    for path in sorted(PROJECT_ROOT.rglob("*")):
        if not path.is_file():
            continue

        if not is_allowed_file(path):
            continue

        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        lines = text.splitlines()

        for idx, line in enumerate(lines, start=1):
            if query_lower in line.lower():
                results.append({
                    "path": str(path.relative_to(PROJECT_ROOT)),
                    "line": idx,
                    "preview": line.strip()[:300],
                })

                if len(results) >= max_results:
                    return {
                        "query": query,
                        "count": len(results),
                        "results": results,
                    }

    return {
        "query": query,
        "count": len(results),
        "results": results,
    }


def project_summary() -> dict[str, Any]:
    folders = []
    files = []
    important_files = []

    for path in sorted(PROJECT_ROOT.iterdir()):
        if is_blocked_path(path):
            continue

        if path.is_dir():
            folders.append(path.name)
        elif path.is_file():
            files.append(path.name)

    candidates = [
        "docker-compose.yml",
        "osiris-api/app/main.py",
        "osiris-api/app/permissions.py",
        "osiris-api/app/device_core.py",
        "osiris-api/app/approvals.py",
        "osiris-api/app/assistant_router.py",
        "website/html/chat.html",
        "website/html/system.html",
        "website/html/devices.html",
        "website/html/approvals.html",
        "host-agent/host_agent.py",
    ]

    for item in candidates:
        path = safe_project_path(item)
        if path.exists():
            important_files.append(item)

    return {
        "project_root": str(PROJECT_ROOT),
        "folders": folders,
        "files": files,
        "important_files": important_files,
        "notes": [
            "Dev Core 1.0 is read-only.",
            "Sensitive files such as .env and keys are blocked.",
            "Large runtime data folders are blocked."
        ]
    }
