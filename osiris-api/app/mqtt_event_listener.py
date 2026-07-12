import json
import os
import threading
from datetime import datetime, timezone
from typing import Any

import paho.mqtt.client as mqtt
import psycopg2
from psycopg2.extras import RealDictCursor


DATABASE_URL = os.getenv("DATABASE_URL")
MQTT_HOST = "mqtt"
MQTT_PORT = 1883

TOPICS = [
    ("osiris/+/status", 0),
    ("osiris/+/events", 0),
]


_listener_started = False


def get_db_connection():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)


def init_device_events_table():
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS device_events (
                    id BIGSERIAL PRIMARY KEY,
                    topic TEXT NOT NULL,
                    device_id TEXT,
                    event_type TEXT,
                    status TEXT,
                    action TEXT,
                    severity TEXT,
                    message TEXT,
                    payload JSONB NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )

            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_device_events_created_at
                ON device_events (created_at DESC);
                """
            )

            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_device_events_device_id
                ON device_events (device_id);
                """
            )

        conn.commit()


def save_device_event(topic: str, payload: dict[str, Any]):
    device_id = payload.get("device_id")
    event_type = payload.get("event")
    status = payload.get("status")
    action = payload.get("action")
    severity = payload.get("severity")
    message = payload.get("message")

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO device_events
                (topic, device_id, event_type, status, action, severity, message, payload)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb);
                """,
                (
                    topic,
                    device_id,
                    event_type,
                    status,
                    action,
                    severity,
                    message,
                    json.dumps(payload),
                ),
            )
        conn.commit()


def get_recent_device_events(limit: int = 50):
    limit = max(1, min(limit, 200))

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    id,
                    topic,
                    device_id,
                    event_type,
                    status,
                    action,
                    severity,
                    message,
                    payload,
                    created_at
                FROM device_events
                ORDER BY created_at DESC
                LIMIT %s;
                """,
                (limit,),
            )
            rows = cur.fetchall()

    return rows


def on_connect(client, userdata, flags, rc):
    for topic, qos in TOPICS:
        client.subscribe(topic, qos)


def on_message(client, userdata, msg):
    try:
        raw = msg.payload.decode(errors="replace")
        payload = json.loads(raw)
    except Exception:
        payload = {
            "device_id": None,
            "event": "parse_error",
            "severity": "error",
            "message": "Failed to parse MQTT payload as JSON.",
            "raw": msg.payload.decode(errors="replace"),
            "received_at": datetime.now(timezone.utc).isoformat(),
        }

    try:
        save_device_event(msg.topic, payload)
    except Exception as exc:
        print(f"[DeviceEvents] Failed to save event: {exc}")


def _listener_loop():
    init_device_events_table()

    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message

    print(f"[DeviceEvents] Connecting to MQTT {MQTT_HOST}:{MQTT_PORT}")
    client.connect(MQTT_HOST, MQTT_PORT, 60)
    client.loop_forever()


def start_device_event_listener():
    global _listener_started

    if _listener_started:
        return

    _listener_started = True

    thread = threading.Thread(
        target=_listener_loop,
        daemon=True,
        name="OsirisDeviceEventListener"
    )
    thread.start()
