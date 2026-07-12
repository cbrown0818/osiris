import json
import time
import uuid
from typing import Any

import paho.mqtt.publish as publish

MQTT_HOST = "mqtt"
MQTT_PORT = 1883


def publish_command(topic: str, payload: dict[str, Any]) -> dict[str, Any]:
    request_id = payload.get("request_id") or str(uuid.uuid4())

    message = {
        "request_id": request_id,
        "timestamp": time.time(),
        **payload,
    }

    publish.single(
        topic,
        payload=json.dumps(message),
        hostname=MQTT_HOST,
        port=MQTT_PORT,
    )

    return {
        "status": "published",
        "topic": topic,
        "request_id": request_id,
        "payload": message,
    }
