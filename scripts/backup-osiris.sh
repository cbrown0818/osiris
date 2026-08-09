#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd -P)"

BACKUP_ROOT="${OSIRIS_PRIVATE_BACKUP_ROOT:-/mnt/vault/osiris-private-backups}"
KEY_FILE="${OSIRIS_BACKUP_KEY_FILE:-$HOME/.config/osiris/backup-passphrase}"
KEEP_BACKUPS="${OSIRIS_BACKUP_RETENTION:-14}"

STAMP="$(date +%Y-%m-%d_%H-%M-%S)"
WORK_DIR="$BACKUP_ROOT/.work-$STAMP-$$"
PLAINTEXT_ARCHIVE="$BACKUP_ROOT/.osiris-private-$STAMP.tar.gz"
ENCRYPTED_ARCHIVE="$BACKUP_ROOT/osiris-private-memory-$STAMP.tar.gz.gpg"
CHECKSUM_FILE="$ENCRYPTED_ARCHIVE.sha256"

POSTGRES_CONTAINER="osiris-postgres"
QDRANT_CONTAINER="osiris-qdrant"
API_CONTAINER="osiris-api"
PROXY_CONTAINER="osiris-proxy"
UPTIME_CONTAINER="osiris-uptime"
MQTT_CONTAINER="osiris-mqtt"
OLLAMA_CONTAINER="osiris-ollama"

cd "$REPO_ROOT"

for command_name in \
    docker \
    python3 \
    tar \
    gpg \
    sha256sum
do
    command -v "$command_name" >/dev/null 2>&1 || {
        echo "Missing required command: $command_name" >&2
        exit 1
    }
done

mkdir -p \
    "$BACKUP_ROOT" \
    "$(dirname "$KEY_FILE")" \
    "$WORK_DIR"

chmod 700 \
    "$BACKUP_ROOT" \
    "$(dirname "$KEY_FILE")" \
    "$WORK_DIR"

if [ ! -s "$KEY_FILE" ]; then
    python3 - <<'PY' > "$KEY_FILE"
import secrets
print(secrets.token_urlsafe(64))
PY

    chmod 600 "$KEY_FILE"
fi


container_running() {
    docker inspect \
        -f '{{.State.Running}}' \
        "$1" \
        2>/dev/null ||
    echo false
}


API_WAS_RUNNING="$(container_running "$API_CONTAINER")"
PROXY_WAS_RUNNING="$(container_running "$PROXY_CONTAINER")"
UPTIME_WAS_RUNNING="$(container_running "$UPTIME_CONTAINER")"
MQTT_WAS_RUNNING="$(container_running "$MQTT_CONTAINER")"


cleanup() {
    status=$?

    trap - EXIT INT TERM

    if [ "$API_WAS_RUNNING" = "true" ]; then
        docker compose start osiris-api \
            >/dev/null 2>&1 || true
    fi

    if [ "$PROXY_WAS_RUNNING" = "true" ]; then
        docker compose start nginx-proxy-manager \
            >/dev/null 2>&1 || true
    fi

    if [ "$UPTIME_WAS_RUNNING" = "true" ]; then
        docker compose start uptime-kuma \
            >/dev/null 2>&1 || true
    fi

    if [ "$MQTT_WAS_RUNNING" = "true" ]; then
        docker compose start mqtt \
            >/dev/null 2>&1 || true
    fi

    if [ -f "$PLAINTEXT_ARCHIVE" ]; then
        shred -u "$PLAINTEXT_ARCHIVE" \
            2>/dev/null ||
        rm -f "$PLAINTEXT_ARCHIVE"
    fi

    if [ -d "$WORK_DIR" ]; then
        find "$WORK_DIR" \
            -type f \
            -exec shred -u {} + \
            2>/dev/null || true

        rm -rf "$WORK_DIR"
    fi

    exit "$status"
}

trap cleanup EXIT INT TERM


echo "======================================================"
echo "OSIRIS PRIVATE BACKUP"
echo "======================================================"


echo
echo "===== VERIFY REQUIRED RUNTIME DIRECTORIES ====="

for required_dir in \
    "$REPO_ROOT/proxy/data" \
    "$REPO_ROOT/proxy/letsencrypt" \
    "$REPO_ROOT/monitoring/uptime-kuma" \
    "$REPO_ROOT/mqtt/data"
do
    if [ ! -d "$required_dir" ]; then
        echo "Missing required runtime directory:"
        echo "  $required_dir"
        exit 1
    fi
done

echo "PASS: required runtime directories present"


echo
echo "===== DETERMINE POSTGRESQL IDENTITY ====="

POSTGRES_USER="$(
    docker exec "$POSTGRES_CONTAINER" \
        printenv POSTGRES_USER
)"

POSTGRES_DB="$(
    docker exec "$POSTGRES_CONTAINER" \
        printenv POSTGRES_DB
)"

if [ -z "$POSTGRES_USER" ] ||
   [ -z "$POSTGRES_DB" ]
then
    echo "Could not determine PostgreSQL identity." >&2
    exit 1
fi

echo "PASS: PostgreSQL identity resolved"


echo
echo "===== PAUSE OSIRIS WRITES ====="

if [ "$API_WAS_RUNNING" = "true" ]; then
    docker compose stop osiris-api >/dev/null
fi

echo "PASS: API write activity paused"


echo
echo "===== POSTGRESQL BACKUP ====="

docker exec "$POSTGRES_CONTAINER" \
    pg_dump \
    -U "$POSTGRES_USER" \
    -d "$POSTGRES_DB" \
    -Fc \
    > "$WORK_DIR/postgres-$POSTGRES_DB.dump"

docker exec -i "$POSTGRES_CONTAINER" \
    pg_restore \
    -l \
    < "$WORK_DIR/postgres-$POSTGRES_DB.dump" \
    >/dev/null

echo "PASS: PostgreSQL dump created and validated"


echo
echo "===== QDRANT FULL-STORAGE SNAPSHOT ====="

docker compose run \
    --rm \
    --no-deps \
    -T \
    --user "$(id -u):$(id -g)" \
    -v "$WORK_DIR:/backup:Z" \
    --entrypoint python \
    osiris-api - <<'PYQDRANT'
import json
import os
import urllib.parse
import urllib.request

base_url = os.getenv(
    "QDRANT_URL",
    "http://qdrant:6333",
).rstrip("/")

api_key = os.getenv(
    "QDRANT__SERVICE__API_KEY",
    "",
).strip()

headers = {}

if api_key:
    headers["api-key"] = api_key

create_request = urllib.request.Request(
    f"{base_url}/snapshots",
    method="POST",
    headers=headers,
)

with urllib.request.urlopen(
    create_request,
    timeout=300,
) as response:
    payload = json.load(response)

snapshot_name = (
    payload
    .get("result", {})
    .get("name")
)

if not snapshot_name:
    raise SystemExit(
        f"Qdrant did not return snapshot name: {payload}"
    )

encoded_name = urllib.parse.quote(
    snapshot_name,
    safe="",
)

download_url = (
    f"{base_url}/snapshots/{encoded_name}"
)

try:
    request = urllib.request.Request(
        download_url,
        headers=headers,
    )

    with urllib.request.urlopen(
        request,
        timeout=600,
    ) as response:
        with open(
            "/backup/qdrant-full.snapshot",
            "wb",
        ) as output:
            while True:
                chunk = response.read(
                    1024 * 1024
                )

                if not chunk:
                    break

                output.write(chunk)

finally:
    try:
        request = urllib.request.Request(
            download_url,
            method="DELETE",
            headers=headers,
        )

        urllib.request.urlopen(
            request,
            timeout=120,
        ).close()

    except Exception:
        pass

if (
    os.path.getsize(
        "/backup/qdrant-full.snapshot"
    ) <= 0
):
    raise SystemExit(
        "Downloaded Qdrant snapshot is empty"
    )

print(snapshot_name)
PYQDRANT

echo "PASS: Qdrant snapshot created"


echo
echo "===== RESUME OSIRIS API ====="

if [ "$API_WAS_RUNNING" = "true" ]; then
    docker compose start osiris-api >/dev/null
fi

echo "PASS: API resumed"


echo
echo "===== CAPTURE OLLAMA MODEL INVENTORY ====="

if [ "$(container_running "$OLLAMA_CONTAINER")" = "true" ]; then
    docker exec "$OLLAMA_CONTAINER" \
        ollama list \
        > "$WORK_DIR/ollama-models.txt"
else
    echo "Ollama container was not running." \
        > "$WORK_DIR/ollama-models.txt"
fi

chmod 600 "$WORK_DIR/ollama-models.txt"

echo "PASS: Ollama inventory recorded"


echo
echo "===== CAPTURE RUNTIME IMAGE INVENTORY ====="

for container in \
    "$PROXY_CONTAINER" \
    osiris-website \
    "$API_CONTAINER" \
    "$POSTGRES_CONTAINER" \
    "$QDRANT_CONTAINER" \
    "$OLLAMA_CONTAINER" \
    "$UPTIME_CONTAINER" \
    "$MQTT_CONTAINER"
do
    docker inspect \
        --format '{{.Name}} {{.Config.Image}}' \
        "$container" \
        2>/dev/null ||
    true
done > "$WORK_DIR/runtime-images.txt"

chmod 600 "$WORK_DIR/runtime-images.txt"

echo "PASS: runtime images recorded"


echo
echo "===== PAUSE FILE-BACKED SERVICES ====="

if [ "$PROXY_WAS_RUNNING" = "true" ]; then
    docker compose stop nginx-proxy-manager >/dev/null
fi

if [ "$UPTIME_WAS_RUNNING" = "true" ]; then
    docker compose stop uptime-kuma >/dev/null
fi

if [ "$MQTT_WAS_RUNNING" = "true" ]; then
    docker compose stop mqtt >/dev/null
fi

echo "PASS: mutable filesystem services paused"


echo
echo "===== ARCHIVE NGINX PROXY MANAGER ====="

tar -czf \
    "$WORK_DIR/npm-data.tar.gz" \
    -C "$REPO_ROOT/proxy" \
    data

tar -tzf \
    "$WORK_DIR/npm-data.tar.gz" \
    >/dev/null

echo "PASS: NPM data archived"


echo
echo "===== ARCHIVE TLS / LETSENCRYPT ====="

tar -czf \
    "$WORK_DIR/npm-letsencrypt.tar.gz" \
    -C "$REPO_ROOT/proxy" \
    letsencrypt

tar -tzf \
    "$WORK_DIR/npm-letsencrypt.tar.gz" \
    >/dev/null

echo "PASS: TLS state archived"


echo
echo "===== ARCHIVE UPTIME KUMA ====="

tar -czf \
    "$WORK_DIR/uptime-kuma.tar.gz" \
    -C "$REPO_ROOT/monitoring" \
    uptime-kuma

tar -tzf \
    "$WORK_DIR/uptime-kuma.tar.gz" \
    >/dev/null

echo "PASS: Uptime Kuma state archived"


echo
echo "===== ARCHIVE MQTT STATE ====="

# Mosquitto persistence files may be owned by the container's
# service account and intentionally unreadable by the host user.
# Read them through the already-installed Mosquitto image rather
# than weakening permissions on the live database.

MQTT_IMAGE="$(
    docker inspect \
        --format '{{.Config.Image}}' \
        "$MQTT_CONTAINER"
)"

HOST_UID="$(id -u)"
HOST_GID="$(id -g)"

docker run \
    --rm \
    --user 0:0 \
    -e HOST_UID="$HOST_UID" \
    -e HOST_GID="$HOST_GID" \
    -v "$REPO_ROOT/mqtt:/mqtt:ro,z" \
    -v "$WORK_DIR:/backup:z" \
    --entrypoint sh \
    "$MQTT_IMAGE" \
    -ec '
        tar -czf /backup/mqtt-data.tar.gz -C /mqtt data
        chown "$HOST_UID:$HOST_GID" /backup/mqtt-data.tar.gz
        chmod 600 /backup/mqtt-data.tar.gz
    '

tar -tzf \
    "$WORK_DIR/mqtt-data.tar.gz" \
    >/dev/null

echo "PASS: MQTT state archived"


echo
echo "===== RESUME FILE-BACKED SERVICES ====="

if [ "$PROXY_WAS_RUNNING" = "true" ]; then
    docker compose start nginx-proxy-manager >/dev/null
fi

if [ "$UPTIME_WAS_RUNNING" = "true" ]; then
    docker compose start uptime-kuma >/dev/null
fi

if [ "$MQTT_WAS_RUNNING" = "true" ]; then
    docker compose start mqtt >/dev/null
fi

echo "PASS: filesystem services resumed"


echo
echo "===== ARCHIVE SOURCE AND CONFIGURATION ====="

SOURCE_ITEMS=()

for item in \
    docker-compose.yml \
    osiris-api \
    website \
    host-agent \
    agents \
    scripts \
    docs \
    mqtt/config
do
    [ -e "$item" ] &&
        SOURCE_ITEMS+=("$item")
done

tar -czf \
    "$WORK_DIR/source-config.tar.gz" \
    --exclude='.git' \
    --exclude='*.before-*' \
    --exclude='*.backup.*' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    -C "$REPO_ROOT" \
    "${SOURCE_ITEMS[@]}"

tar -tzf \
    "$WORK_DIR/source-config.tar.gz" \
    >/dev/null

echo "PASS: source/config archived"


echo
echo "===== COPY PRIVATE ENVIRONMENT ====="

if [ ! -f .env ]; then
    echo "FAIL: .env is missing"
    exit 1
fi

cp .env \
    "$WORK_DIR/private.env"

chmod 600 \
    "$WORK_DIR/private.env"

echo "PASS: private environment included"


echo
echo "===== CREATE MANIFEST ====="

cat > "$WORK_DIR/manifest.txt" <<EOF_MANIFEST
created=$STAMP
host=$(hostname)
repository=$REPO_ROOT
postgres_database=$POSTGRES_DB
postgres_user=$POSTGRES_USER
contents=postgres_dump,qdrant_full_snapshot,source_config,private_env,npm_data,npm_letsencrypt,uptime_kuma,mqtt_data,ollama_model_inventory,runtime_image_inventory
encryption=gpg_symmetric_aes256
EOF_MANIFEST

chmod 600 "$WORK_DIR/manifest.txt"


echo
echo "===== INTERNAL CHECKSUMS ====="

(
    cd "$WORK_DIR"

    sha256sum \
        postgres-"$POSTGRES_DB".dump \
        qdrant-full.snapshot \
        source-config.tar.gz \
        private.env \
        npm-data.tar.gz \
        npm-letsencrypt.tar.gz \
        uptime-kuma.tar.gz \
        mqtt-data.tar.gz \
        ollama-models.txt \
        runtime-images.txt \
        manifest.txt \
        > CONTENTS.sha256
)

echo "PASS: internal checksums generated"


echo
echo "===== CREATE PLAINTEXT ARCHIVE ====="

tar -czf \
    "$PLAINTEXT_ARCHIVE" \
    -C "$WORK_DIR" \
    .

chmod 600 "$PLAINTEXT_ARCHIVE"


echo
echo "===== ENCRYPT BACKUP ====="

gpg \
    --batch \
    --yes \
    --pinentry-mode loopback \
    --passphrase-file "$KEY_FILE" \
    --symmetric \
    --cipher-algo AES256 \
    --compress-algo none \
    --output "$ENCRYPTED_ARCHIVE" \
    "$PLAINTEXT_ARCHIVE"

chmod 600 "$ENCRYPTED_ARCHIVE"


echo
echo "===== EXTERNAL CHECKSUM ====="

sha256sum \
    "$ENCRYPTED_ARCHIVE" \
    > "$CHECKSUM_FILE"

chmod 600 "$CHECKSUM_FILE"


echo
echo "===== VERIFY ENCRYPTED ARCHIVE ====="

gpg \
    --batch \
    --quiet \
    --pinentry-mode loopback \
    --passphrase-file "$KEY_FILE" \
    --decrypt "$ENCRYPTED_ARCHIVE" \
    2>/dev/null |
tar -tzf - \
    >/dev/null

echo "PASS: encrypted archive decrypts and lists"


echo
echo "===== RETENTION ====="

mapfile -t BACKUPS < <(
    find "$BACKUP_ROOT" \
        -maxdepth 1 \
        -type f \
        -name 'osiris-private-memory-*.tar.gz.gpg' \
        -printf '%T@ %p\n' |
    sort -nr |
    cut -d' ' -f2-
)

if [ "${#BACKUPS[@]}" -gt "$KEEP_BACKUPS" ]; then
    for ((
        index=KEEP_BACKUPS;
        index<${#BACKUPS[@]};
        index++
    ))
    do
        rm -f \
            "${BACKUPS[$index]}" \
            "${BACKUPS[$index]}.sha256"
    done
fi

echo "PASS: retention policy applied"


echo
echo "======================================================"
echo "OSIRIS PRIVATE BACKUP: PASS"
echo "======================================================"

echo "Encrypted archive:"
echo "  $ENCRYPTED_ARCHIVE"

echo "Checksum:"
echo "  $CHECKSUM_FILE"

echo "Recovery key:"
echo "  $KEY_FILE"
