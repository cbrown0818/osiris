from pathlib import Path
import argparse

ROOT = Path.cwd().resolve()

ALLOWED_TOP_DIRS = {
    "lilith-api",
    "host-agent",
    "agents",
    "scripts",
    "website",
}

ALLOWED_TOP_FILES = {
    ".env",
    "docker-compose.yml",
    "docker-compose.yml.before-ollama-gpu",
}

SKIP_DIR_NAMES = {
    ".git",
    ".venv",
    "__pycache__",
    "node_modules",
    "backups",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "logs",
    "migrations",
}

SKIP_PREFIXES = {
    ("postgres", "data"),
    ("qdrant", "data"),
    ("qdrant", "storage"),
    ("ollama", "data"),
    ("proxy", "data"),
    ("nginx-proxy-manager", "data"),
    ("nginx-proxy-manager", "letsencrypt"),
}

SKIP_SUFFIXES = {
    ".pyc", ".pyo", ".so", ".db", ".sqlite", ".sqlite3",
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".svg",
    ".pdf", ".zip", ".tar", ".gz", ".tgz", ".7z",
    ".pptx", ".docx", ".xlsx",
    ".mp4", ".mov", ".avi", ".mkv",
    ".woff", ".woff2", ".ttf", ".otf",
    ".log",
}

SKIP_NAME_CONTAINS = {
    ".backup.",
    ".before-",
    ".tar.gz",
    ".sha256",
}

REPLACEMENTS = [
    ("LILITH", "OSIRIS"),
    ("Lilith", "Osiris"),
    ("lilith", "osiris"),
]

# Keep existing Qdrant collection names stable for now.
# Branding can change without breaking document memory.
PROTECTED_RESTORES = [
    ("osiris_documents", "lilith_documents"),
    ("osiris_memories", "lilith_memories"),
]


def rel_parts(path: Path) -> tuple[str, ...]:
    return path.relative_to(ROOT).parts


def has_prefix(parts: tuple[str, ...], prefix: tuple[str, ...]) -> bool:
    return len(parts) >= len(prefix) and parts[:len(prefix)] == prefix


def allowed_scope(path: Path) -> bool:
    parts = rel_parts(path)

    if not parts:
        return False

    first = parts[0]

    if first in ALLOWED_TOP_FILES:
        return True

    if first in ALLOWED_TOP_DIRS:
        return True

    return False


def should_skip(path: Path) -> bool:
    parts = rel_parts(path)

    if not allowed_scope(path):
        return True

    if any(part in SKIP_DIR_NAMES for part in parts):
        return True

    if any(has_prefix(parts, prefix) for prefix in SKIP_PREFIXES):
        return True

    name = path.name

    if any(token in name for token in SKIP_NAME_CONTAINS):
        return True

    if path.suffix.lower() in SKIP_SUFFIXES:
        return True

    return False


def replace_text(path: Path, dry_run: bool) -> bool:
    if should_skip(path) or not path.is_file():
        return False

    try:
        raw = path.read_bytes()
    except Exception:
        return False

    if b"\x00" in raw:
        return False

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return False

    new_text = text

    for old, new in REPLACEMENTS:
        new_text = new_text.replace(old, new)

    for new_value, original_value in PROTECTED_RESTORES:
        new_text = new_text.replace(new_value, original_value)

    if new_text == text:
        return False

    print(f"[TEXT] {path.relative_to(ROOT)}")

    if not dry_run:
        path.write_text(new_text, encoding="utf-8")

    return True


def renamed_path(path: Path) -> Path:
    new_name = path.name

    for old, new in REPLACEMENTS:
        new_name = new_name.replace(old, new)

    if new_name == path.name:
        return path

    return path.with_name(new_name)


def rename_paths(dry_run: bool) -> int:
    renamed = 0

    all_paths = sorted(
        [p for p in ROOT.rglob("*") if not should_skip(p)],
        key=lambda p: len(p.parts),
        reverse=True,
    )

    for path in all_paths:
        new_path = renamed_path(path)

        if new_path == path:
            continue

        if new_path.exists():
            print(f"[SKIP RENAME EXISTS] {path.relative_to(ROOT)} -> {new_path.relative_to(ROOT)}")
            continue

        print(f"[RENAME] {path.relative_to(ROOT)} -> {new_path.relative_to(ROOT)}")

        if not dry_run:
            path.rename(new_path)

        renamed += 1

    return renamed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Actually modify files.")
    args = parser.parse_args()

    dry_run = not args.apply

    print("OSIRIS rename migration")
    print(f"Root: {ROOT}")
    print(f"Mode: {'APPLY' if args.apply else 'DRY RUN'}")
    print()

    changed_files = 0

    for path in ROOT.rglob("*"):
        if path.is_file() and replace_text(path, dry_run):
            changed_files += 1

    renamed_count = rename_paths(dry_run)

    print()
    print("Summary")
    print(f"Text files changed: {changed_files}")
    print(f"Paths renamed: {renamed_count}")

    if dry_run:
        print()
        print("Dry run only. Run again with --apply to make changes.")


if __name__ == "__main__":
    main()
