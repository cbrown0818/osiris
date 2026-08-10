#!/usr/bin/env bash
set -Eeuo pipefail

MODE="${1:---staged}"

failures=0

# ------------------------------------------------------------
# OSIRIS ZERO-PERSONAL-CONTENT POLICY
# ------------------------------------------------------------

RISKY_PATH_PATTERN='(^|/)(uploads?|attachments?|screenshots?|photos?|generated[-_]?images?|user[-_]?images?|chat[-_]?logs?|chat[-_]?exports?|conversation[-_]?exports?|memory[-_]?exports?|transcripts?|sessions?|session[-_]?data|private[-_]?data|personal[-_]?data|user[-_]?data|private[-_]?backups?)(/|$)'

FORBIDDEN_FILE_PATTERN='(^|/)\.env($|\.)|\.(png|jpe?g|webp|gif|bmp|tiff?|heic|avif|db|sqlite|sqlite3|sql|dump|jsonl|ndjson|log|pem|key|p12|pfx|gpg|age|docx|xlsx|pptx|7z|rar)$'

# Generic, version-controlled SQL schema migrations are allowed only
# under this exact source path and naming convention.
MIGRATION_SQL_PATTERN='^osiris-api/db/migrations/[0-9]{3}_[a-z0-9_]+\.sql$'


LOCAL_SETTINGS_PATTERN='(^|/)\.vscode/|(^|/)\.idea/|(^|/)(credentials?|secrets?|personal[-_]?settings?|user[-_]?settings?)(\.|/)'

SECRET_PATTERN='-----BEGIN ([A-Z ]+)?PRIVATE KEY-----|OSIRIS_API_TOKEN=[A-Za-z0-9_-]{32,}|github_pat_[A-Za-z0-9_]+|gh[pousr]_[A-Za-z0-9]+|sk-[A-Za-z0-9_-]{20,}|AKIA[0-9A-Z]{16}|DATABASE_URL=.*://[^[:space:]]+:[^@[:space:]]+@'


block() {
    printf 'BLOCKED: %s\n' "$1"
    failures=1
}


check_path() {
    local path="$1"

    # Generic configuration template is explicitly permitted.
    if [ "$path" = ".env.example" ]; then
        return
    fi

    if printf '%s\n' "$path" |
        grep -Eiq "$RISKY_PATH_PATTERN"
    then
        block "private-data path: $path"
    fi

    if printf '%s\n' "$path" |
        grep -Eiq "$FORBIDDEN_FILE_PATTERN"
    then
        if ! printf '%s\n' "$path" |
            grep -Eq "$MIGRATION_SQL_PATTERN"
        then
            block "forbidden file type/path: $path"
        fi
    fi

    if printf '%s\n' "$path" |
        grep -Eiq "$LOCAL_SETTINGS_PATTERN"
    then
        block "personal/local settings path: $path"
    fi
}


is_transcript_candidate() {
    local path="$1"

    # Source code commonly contains words such as prompt/question/response.
    # Only data/document-like files receive transcript-content analysis.
    case "${path,,}" in
        *.txt|*.json|*.jsonl|*.ndjson|*.log|*.csv|*.md|*.yaml|*.yml)
            return 0
            ;;
        *)
            return 1
            ;;
    esac
}


contains_transcript() {
    local file="$1"

    # JSON-style conversation containing BOTH user and assistant roles.
    if grep -IEqu \
        '"role"[[:space:]]*:[[:space:]]*"(user|human)"' \
        "$file" 2>/dev/null &&
       grep -IEqu \
        '"role"[[:space:]]*:[[:space:]]*"assistant"' \
        "$file" 2>/dev/null
    then
        return 0
    fi

    # Plain-text transcript containing BOTH sides.
    if grep -IEqu \
        '^[[:space:]]*(User|Human):[[:space:]]' \
        "$file" 2>/dev/null &&
       grep -IEqu \
        '^[[:space:]]*Assistant:[[:space:]]' \
        "$file" 2>/dev/null
    then
        return 0
    fi

    # Common exported-conversation structures.
    if grep -IEqu \
        '"author"[[:space:]]*:[[:space:]]*\{[^}]*"role"[[:space:]]*:[[:space:]]*"(user|assistant)"' \
        "$file" 2>/dev/null
    then
        return 0
    fi

    return 1
}


check_content_file() {
    local path="$1"
    local file="$2"
    local mime=""

    # The scanner contains literal secret detection expressions itself.
    # Do not make the guard dog arrest its own reflection.
    if [ "$path" = "scripts/git-privacy-check.sh" ]; then
        return
    fi

    mime="$(file --brief --mime-type "$file" 2>/dev/null || true)"

    case "$mime" in
        image/*)
            block "actual image content detected: $path"
            ;;
    esac

    if grep -IEm1 "$SECRET_PATTERN" "$file" \
        >/dev/null 2>&1
    then
        block "secret-like content detected: $path"
    fi

    if is_transcript_candidate "$path"; then
        if contains_transcript "$file"; then
            block "conversation transcript-like content detected: $path"
        fi
    fi
}


check_staged_file() {
    local path="$1"
    local tmp

    check_path "$path"

    if ! git cat-file -e ":$path" 2>/dev/null; then
        return
    fi

    tmp="$(mktemp)"
    git show ":$path" > "$tmp"

    check_content_file "$path" "$tmp"

    rm -f "$tmp"
}


check_worktree_file() {
    local path="$1"

    check_path "$path"

    if [ -f "$path" ]; then
        check_content_file "$path" "$path"
    fi
}


check_history() {
    local oid path type tmp

    while read -r oid path; do

        [ -n "${oid:-}" ] || continue
        [ -n "${path:-}" ] || continue

        check_path "$path"

        type="$(git cat-file -t "$oid" 2>/dev/null || true)"

        [ "$type" = "blob" ] || continue

        tmp="$(mktemp)"

        if git cat-file blob "$oid" > "$tmp" 2>/dev/null; then
            check_content_file "$path" "$tmp"
        fi

        rm -f "$tmp"

    done < <(
        git rev-list --objects --all |
        sort -u
    )
}


case "$MODE" in

    --staged)

        while IFS= read -r -d '' path; do
            [ -n "$path" ] || continue
            check_staged_file "$path"
        done < <(
            git diff \
                --cached \
                --name-only \
                --diff-filter=ACMR \
                -z
        )

        ;;


    --all-tracked)

        while IFS= read -r -d '' path; do
            [ -n "$path" ] || continue
            check_worktree_file "$path"
        done < <(
            git ls-files -z
        )

        ;;


    --history)

        check_history

        ;;


    *)

        echo "Usage:"
        echo "  $0 --staged"
        echo "  $0 --all-tracked"
        echo "  $0 --history"
        exit 2

        ;;

esac


echo

if [ "$failures" -ne 0 ]; then

    echo "======================================================"
    echo "OSIRIS PRIVACY CHECK FAILED"
    echo "Nothing should be committed or pushed."
    echo "======================================================"

    exit 1
fi

echo "======================================================"
echo "OSIRIS PRIVACY CHECK PASSED"
echo "Mode: $MODE"
echo "======================================================"

exit 0
