import difflib
import json
import os
import uuid
from pathlib import Path
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor

from dev_core import read_file, safe_project_path, is_allowed_file, is_blocked_path, DevCoreError, PROJECT_ROOT


DATABASE_URL = os.getenv("DATABASE_URL")


def get_db_connection():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)


def init_patches_table():
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS patches (
                    id UUID PRIMARY KEY,
                    status TEXT NOT NULL DEFAULT 'pending',
                    file_path TEXT NOT NULL,
                    original_content TEXT NOT NULL,
                    proposed_content TEXT NOT NULL,
                    diff TEXT NOT NULL,
                    reason TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    decided_at TIMESTAMPTZ,
                    result JSONB
                );
                """
            )

            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_patches_status_created
                ON patches (status, created_at DESC);
                """
            )

        conn.commit()


def make_diff(file_path: str, original: str, proposed: str) -> str:
    return "".join(
        difflib.unified_diff(
            original.splitlines(keepends=True),
            proposed.splitlines(keepends=True),
            fromfile=f"{file_path} original",
            tofile=f"{file_path} proposed",
        )
    )


def create_patch(
    file_path: str,
    proposed_content: str,
    reason: str | None = None,
) -> dict[str, Any]:
    init_patches_table()

    file_data = read_file(file_path, max_bytes=500_000)
    original_content = file_data["content"]

    path = safe_project_path(file_path)

    if not is_allowed_file(path):
        raise DevCoreError(f"File is blocked or unsupported: {file_path}")

    patch_id = str(uuid.uuid4())
    diff = make_diff(file_path, original_content, proposed_content)

    if not diff.strip():
        raise DevCoreError("No changes detected. Patch was not created.")

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO patches
                (id, status, file_path, original_content, proposed_content, diff, reason)
                VALUES (%s, 'pending', %s, %s, %s, %s, %s)
                RETURNING *;
                """,
                (
                    patch_id,
                    file_path,
                    original_content,
                    proposed_content,
                    diff,
                    reason,
                ),
            )
            row = cur.fetchone()
        conn.commit()

    return dict(row)


def list_pending_patches(limit: int = 50) -> list[dict[str, Any]]:
    init_patches_table()
    limit = max(1, min(limit, 200))

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, status, file_path, diff, reason, created_at, decided_at, result
                FROM patches
                WHERE status = 'pending'
                ORDER BY created_at DESC
                LIMIT %s;
                """,
                (limit,),
            )
            rows = cur.fetchall()

    return [dict(row) for row in rows]


def get_patch(patch_id: str) -> dict[str, Any] | None:
    init_patches_table()

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM patches
                WHERE id = %s;
                """,
                (patch_id,),
            )
            row = cur.fetchone()

    return dict(row) if row else None


def deny_patch(patch_id: str) -> dict[str, Any]:
    init_patches_table()

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE patches
                SET status = 'denied',
                    decided_at = NOW(),
                    result = %s::jsonb
                WHERE id = %s
                RETURNING *;
                """,
                (
                    json.dumps({"message": "Patch denied by Master."}),
                    patch_id,
                ),
            )
            row = cur.fetchone()
        conn.commit()

    if not row:
        raise DevCoreError(f"Patch not found: {patch_id}")

    return dict(row)


def apply_patch(patch_id: str) -> dict[str, Any]:
    init_patches_table()

    patch = get_patch(patch_id)
    if not patch:
        raise DevCoreError(f"Patch not found: {patch_id}")

    if patch["status"] != "pending":
        raise DevCoreError(f"Patch is not pending. Current status: {patch['status']}")

    file_path = patch["file_path"]
    path = safe_project_path(file_path)

    if not is_allowed_file(path):
        raise DevCoreError(f"File is blocked or unsupported: {file_path}")

    if not path.exists() or not path.is_file():
        raise DevCoreError(f"Target file does not exist: {file_path}")

    current_content = path.read_text(encoding="utf-8", errors="replace")
    original_content = patch["original_content"]
    proposed_content = patch["proposed_content"]

    if current_content != original_content:
        raise DevCoreError(
            "Target file has changed since the patch was created. "
            "Create a fresh patch before applying."
        )

    validation = validate_proposed_content(file_path, proposed_content)

    if not validation.get("ok"):
        raise DevCoreError(
            "Patch validation failed: "
            + "; ".join(validation.get("errors", ["unknown validation error"]))
        )

    import datetime

    timestamp = datetime.datetime.now().strftime("%Y-%m-%d-%H%M%S")
    backup_path = path.with_name(f"{path.name}.backup.patch.{timestamp}")

    backup_path.write_text(current_content, encoding="utf-8")
    path.write_text(proposed_content, encoding="utf-8")

    post_apply_check = run_post_apply_check(file_path)
    affected_service = detect_affected_service(file_path)

    result = {
        "message": "Patch applied successfully.",
        "file_path": file_path,
        "backup_path": str(backup_path.relative_to(PROJECT_ROOT)),
        "validation": validation,
        "post_apply_check": post_apply_check,
        "affected_service": affected_service,
    }

    if not post_apply_check.get("ok"):
        result["message"] = "Patch applied, but post-apply health check failed."

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE patches
                SET status = 'applied',
                    decided_at = NOW(),
                    result = %s::jsonb
                WHERE id = %s
                RETURNING *;
                """,
                (
                    json.dumps(result),
                    patch_id,
                ),
            )
            row = cur.fetchone()
        conn.commit()

    return {
        "status": "applied",
        "patch": dict(row),
        "result": result,
    }

async def generate_patch_with_ai(
    file_path: str,
    instruction: str,
    model: str = "qwen2.5-coder:7b",
) -> dict[str, Any]:
    import httpx

    file_data = read_file(file_path, max_bytes=120_000)
    original_content = file_data["content"]

    prompt = (
        "You are editing a source code file for the Osiris local AI project.\\n\\n"
        f"Task:\\n{instruction}\\n\\n"
        f"File path:\\n{file_path}\\n\\n"
        "Current file content:\\n"
        "-----BEGIN FILE-----\\n"
        f"{original_content}\\n"
        "-----END FILE-----\\n\\n"
        "Return ONLY the complete updated file content. "
        "Do not include markdown fences. "
        "Do not explain the change. "
        "Do not omit unchanged parts."
    )

    ollama_url = os.getenv("OLLAMA_URL", "http://ollama:11434")

    async with httpx.AsyncClient(timeout=240.0) as client:
        response = await client.post(
            f"{ollama_url}/api/chat",
            json={
                "model": model,
                "messages": [
                    {
                        "role": "system",
                        "content": "You are a precise coding assistant. Return only complete file contents when asked to edit files.",
                    },
                    {
                        "role": "user",
                        "content": prompt,
                    },
                ],
                "stream": False,
            },
        )
        response.raise_for_status()
        data = response.json()

    proposed_content = data.get("message", {}).get("content", "").strip()

    if proposed_content.startswith("```"):
        lines = proposed_content.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        proposed_content = "\\n".join(lines).strip()

    if not proposed_content:
        raise DevCoreError("AI returned empty proposed content.")

    if original_content.endswith("\\n") and not proposed_content.endswith("\\n"):
        proposed_content += "\\n"

    patch = create_patch(
        file_path=file_path,
        proposed_content=proposed_content,
        reason=f"AI-generated patch: {instruction}",
    )

    return {
        "status": "pending",
        "file_path": file_path,
        "instruction": instruction,
        "model": model,
        "patch": patch,
    }



def validate_proposed_content(file_path: str, proposed_content: str) -> dict[str, Any]:
    import json as json_module
    import subprocess
    import tempfile

    path = safe_project_path(file_path)
    suffix = path.suffix.lower()
    name = path.name

    result = {
        "ok": True,
        "file_path": file_path,
        "checks": [],
        "errors": [],
        "warnings": [],
    }

    if proposed_content is None or proposed_content == "":
        result["ok"] = False
        result["errors"].append("Proposed content is empty.")
        return result

    if len(proposed_content.encode("utf-8")) > 750_000:
        result["ok"] = False
        result["errors"].append("Proposed content is too large.")
        return result

    if suffix == ".py":
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as tmp:
            tmp.write(proposed_content)
            tmp_path = tmp.name

        proc = subprocess.run(
            ["python", "-m", "py_compile", tmp_path],
            capture_output=True,
            text=True,
            timeout=20,
        )

        if proc.returncode == 0:
            result["checks"].append("Python syntax validation passed.")
        else:
            result["ok"] = False
            result["errors"].append(proc.stderr.strip() or "Python syntax validation failed.")

    elif suffix == ".json":
        try:
            json_module.loads(proposed_content)
            result["checks"].append("JSON validation passed.")
        except Exception as exc:
            result["ok"] = False
            result["errors"].append(f"JSON validation failed: {exc}")

    elif suffix in [".yml", ".yaml"] or name == "docker-compose.yml":
        required_signals = ["services:", ":"]
        missing = [signal for signal in required_signals if signal not in proposed_content]

        if missing:
            result["ok"] = False
            result["errors"].append(f"YAML/Compose sanity check failed. Missing: {', '.join(missing)}")
        else:
            result["checks"].append("YAML/Compose basic sanity check passed.")

        if "\t" in proposed_content:
            result["warnings"].append("YAML contains tab characters; YAML usually expects spaces.")

    elif suffix == ".sh":
        with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False, encoding="utf-8") as tmp:
            tmp.write(proposed_content)
            tmp_path = tmp.name

        proc = subprocess.run(
            ["sh", "-n", tmp_path],
            capture_output=True,
            text=True,
            timeout=20,
        )

        if proc.returncode == 0:
            result["checks"].append("Shell syntax validation passed.")
        else:
            result["ok"] = False
            result["errors"].append(proc.stderr.strip() or "Shell syntax validation failed.")

    elif suffix == ".html":
        lowered = proposed_content.lower()

        if "<html" not in lowered or "</html>" not in lowered:
            result["warnings"].append("HTML does not contain full <html>...</html> structure.")
        else:
            result["checks"].append("HTML document structure sanity check passed.")

        if "<script" in lowered and "</script>" not in lowered:
            result["ok"] = False
            result["errors"].append("HTML contains an opening <script> tag without a closing </script> tag.")

    else:
        result["checks"].append("No specific validator for this file type; basic non-empty check passed.")

    return result


def list_patch_backups() -> list[dict[str, Any]]:
    backups = []

    for path in PROJECT_ROOT.rglob("*"):
        if not path.is_file():
            continue

        if ".backup.patch." not in path.name:
            continue

        # Patch backups are intentionally allowed here even though
        # general Dev Core hides .backup.* files from normal browsing.
        original_name = path.name.split(".backup.patch.")[0]
        relative_backup = str(path.relative_to(PROJECT_ROOT))
        relative_dir = path.parent.relative_to(PROJECT_ROOT)
        original_path = str(relative_dir / original_name)

        backups.append(
            {
                "backup_path": relative_backup,
                "original_path": original_path,
                "size_bytes": path.stat().st_size,
                "modified_at": path.stat().st_mtime,
            }
        )

    backups.sort(key=lambda item: item["modified_at"], reverse=True)
    return backups


def restore_patch_backup(backup_path: str) -> dict[str, Any]:
    backup = safe_project_path(backup_path)

    if not backup.exists() or not backup.is_file():
        raise DevCoreError(f"Backup file does not exist: {backup_path}")

    if ".backup.patch." not in backup.name:
        raise DevCoreError("Only patch backup files can be restored.")

    # Patch backups are intentionally allowed here even though
    # general Dev Core hides .backup.* files from normal browsing.
    original_name = backup.name.split(".backup.patch.")[0]
    original = backup.with_name(original_name)

    if not is_allowed_file(original):
        raise DevCoreError(f"Original target is blocked or unsupported: {original_name}")

    backup_content = backup.read_text(encoding="utf-8", errors="replace")

    validation = validate_proposed_content(
        str(original.relative_to(PROJECT_ROOT)),
        backup_content,
    )

    if not validation.get("ok"):
        raise DevCoreError(
            "Backup restore validation failed: "
            + "; ".join(validation.get("errors", ["unknown validation error"]))
        )

    import datetime

    timestamp = datetime.datetime.now().strftime("%Y-%m-%d-%H%M%S")
    pre_restore_backup = original.with_name(f"{original.name}.backup.pre-restore.{timestamp}")

    if original.exists():
        current_content = original.read_text(encoding="utf-8", errors="replace")
        pre_restore_backup.write_text(current_content, encoding="utf-8")

    original.write_text(backup_content, encoding="utf-8")

    return {
        "status": "restored",
        "backup_path": str(backup.relative_to(PROJECT_ROOT)),
        "restored_to": str(original.relative_to(PROJECT_ROOT)),
        "pre_restore_backup": str(pre_restore_backup.relative_to(PROJECT_ROOT)) if pre_restore_backup.exists() else None,
        "validation": validation,
    }


def list_patch_backups() -> list[dict[str, Any]]:
    backups = []

    for path in PROJECT_ROOT.rglob("*"):
        if not path.is_file():
            continue

        if ".backup.patch." not in path.name:
            continue

        # Patch backups are intentionally allowed here even though
        # general Dev Core hides .backup.* files from normal browsing.
        original_name = path.name.split(".backup.patch.")[0]
        relative_backup = str(path.relative_to(PROJECT_ROOT))
        relative_dir = path.parent.relative_to(PROJECT_ROOT)
        original_path = str(relative_dir / original_name)

        backups.append(
            {
                "backup_path": relative_backup,
                "original_path": original_path,
                "size_bytes": path.stat().st_size,
                "modified_at": path.stat().st_mtime,
            }
        )

    backups.sort(key=lambda item: item["modified_at"], reverse=True)
    return backups


def restore_patch_backup(backup_path: str) -> dict[str, Any]:
    backup = safe_project_path(backup_path)

    if not backup.exists() or not backup.is_file():
        raise DevCoreError(f"Backup file does not exist: {backup_path}")

    if ".backup.patch." not in backup.name:
        raise DevCoreError("Only patch backup files can be restored.")

    # Patch backups are intentionally allowed here even though
    # general Dev Core hides .backup.* files from normal browsing.
    original_name = backup.name.split(".backup.patch.")[0]
    original = backup.with_name(original_name)

    if not is_allowed_file(original):
        raise DevCoreError(f"Original target is blocked or unsupported: {original_name}")

    backup_content = backup.read_text(encoding="utf-8", errors="replace")

    validation = validate_proposed_content(
        str(original.relative_to(PROJECT_ROOT)),
        backup_content,
    )

    if not validation.get("ok"):
        raise DevCoreError(
            "Backup restore validation failed: "
            + "; ".join(validation.get("errors", ["unknown validation error"]))
        )

    import datetime

    timestamp = datetime.datetime.now().strftime("%Y-%m-%d-%H%M%S")
    pre_restore_backup = original.with_name(f"{original.name}.backup.pre-restore.{timestamp}")

    if original.exists():
        current_content = original.read_text(encoding="utf-8", errors="replace")
        pre_restore_backup.write_text(current_content, encoding="utf-8")

    original.write_text(backup_content, encoding="utf-8")

    return {
        "status": "restored",
        "backup_path": str(backup.relative_to(PROJECT_ROOT)),
        "restored_to": str(original.relative_to(PROJECT_ROOT)),
        "pre_restore_backup": str(pre_restore_backup.relative_to(PROJECT_ROOT)) if pre_restore_backup.exists() else None,
        "validation": validation,
    }


def run_post_apply_check(file_path: str) -> dict[str, Any]:
    import json as json_module
    import subprocess

    path = safe_project_path(file_path)
    suffix = path.suffix.lower()
    name = path.name

    result = {
        "ok": True,
        "file_path": file_path,
        "checks": [],
        "errors": [],
        "warnings": [],
    }

    if not path.exists():
        result["ok"] = False
        result["errors"].append("File does not exist after apply.")
        return result

    if suffix == ".py":
        proc = subprocess.run(
            ["python", "-m", "py_compile", str(path)],
            capture_output=True,
            text=True,
            timeout=20,
        )

        if proc.returncode == 0:
            result["checks"].append("Post-apply Python syntax check passed.")
        else:
            result["ok"] = False
            result["errors"].append(proc.stderr.strip() or "Post-apply Python syntax check failed.")

    elif suffix == ".sh":
        proc = subprocess.run(
            ["sh", "-n", str(path)],
            capture_output=True,
            text=True,
            timeout=20,
        )

        if proc.returncode == 0:
            result["checks"].append("Post-apply shell syntax check passed.")
        else:
            result["ok"] = False
            result["errors"].append(proc.stderr.strip() or "Post-apply shell syntax check failed.")

    elif suffix == ".json":
        try:
            json_module.loads(path.read_text(encoding="utf-8"))
            result["checks"].append("Post-apply JSON parse check passed.")
        except Exception as exc:
            result["ok"] = False
            result["errors"].append(f"Post-apply JSON parse check failed: {exc}")

    elif suffix in [".yml", ".yaml"] or name == "docker-compose.yml":
        content = path.read_text(encoding="utf-8", errors="replace")

        if ":" not in content:
            result["ok"] = False
            result["errors"].append("Post-apply YAML sanity check failed: no ':' found.")
        else:
            result["checks"].append("Post-apply YAML basic sanity check passed.")

        if name == "docker-compose.yml":
            proc = subprocess.run(
                ["docker", "compose", "config"],
                cwd=str(PROJECT_ROOT),
                capture_output=True,
                text=True,
                timeout=30,
            )

            if proc.returncode == 0:
                result["checks"].append("Post-apply docker compose config check passed.")
            else:
                result["ok"] = False
                result["errors"].append(proc.stderr.strip() or "docker compose config failed.")

    elif suffix == ".html":
        content = path.read_text(encoding="utf-8", errors="replace").lower()

        if "<script" in content and "</script>" not in content:
            result["ok"] = False
            result["errors"].append("Post-apply HTML check failed: unclosed <script> tag.")
        else:
            result["checks"].append("Post-apply HTML basic sanity check passed.")

    else:
        result["checks"].append("No specific post-apply checker for this file type.")

    return result


def detect_affected_service(file_path: str) -> dict[str, Any]:
    affected = {
        "service": None,
        "risk": "low",
        "recommended_actions": [],
        "notes": [],
    }

    if file_path == "host-agent/host_agent.py":
        affected["service"] = "osiris-host-agent"
        affected["risk"] = "medium"
        affected["recommended_actions"] = [
            "sudo systemctl restart osiris-host-agent",
            "curl http://172.17.0.1:5055/health",
            "curl http://localhost:8000/security/status",
        ]
        affected["notes"].append("Host Agent code changed. Restart Host Agent and verify health.")

    elif file_path.startswith("osiris-api/app/") and file_path.endswith(".py"):
        affected["service"] = "osiris-api"
        affected["risk"] = "medium"
        affected["recommended_actions"] = [
            "docker compose restart osiris-api",
            "curl http://localhost:8000/health",
            "curl http://localhost:8000/security/status",
        ]
        affected["notes"].append("Osiris API code changed. Restart API and verify health.")

    elif file_path.startswith("website/html/") and file_path.endswith(".html"):
        page = file_path.replace("website/html/", "")
        affected["service"] = "osiris-website"
        affected["risk"] = "low"
        affected["recommended_actions"] = [
            "docker compose restart website",
            f"curl -I http://localhost:8088/{page}",
        ]
        affected["notes"].append("Website HTML changed. Verify the page loads.")

    elif file_path == "docker-compose.yml":
        affected["service"] = "docker-compose"
        affected["risk"] = "high"
        affected["recommended_actions"] = [
            "docker compose config",
            "docker compose up -d",
            "./scripts/status-osiris.sh",
        ]
        affected["notes"].append("Docker Compose changed. Validate config before recreating services.")

    return affected
