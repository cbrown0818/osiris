import json
import socket
import time
from typing import Any

import paho.mqtt.client as mqtt


DEVICE_ID = "pi_robot_1"

# Use your tower LAN IP here.
# From your previous setup, this may be 192.168.4.120.
MQTT_BROKER = "192.168.4.120"
MQTT_PORT = 1883

COMMAND_TOPIC = f"osiris/{DEVICE_ID}/command"
STATUS_TOPIC = f"osiris/{DEVICE_ID}/status"
EVENT_TOPIC = f"osiris/{DEVICE_ID}/events"


def publish(client: mqtt.Client, topic: str, payload: dict[str, Any]) -> None:
    message = {
        "device_id": DEVICE_ID,
        "hostname": socket.gethostname(),
        "timestamp": time.time(),
        **payload,
    }

    client.publish(topic, json.dumps(message))


def publish_status(client: mqtt.Client, payload: dict[str, Any]) -> None:
    publish(client, STATUS_TOPIC, payload)


def publish_event(client: mqtt.Client, payload: dict[str, Any]) -> None:
    publish(client, EVENT_TOPIC, payload)


def handle_status(client: mqtt.Client, payload: dict[str, Any]) -> None:
    publish_status(client, {
        "status": "online",
        "message": "Pi agent is online.",
        "received_request_id": payload.get("request_id")
    })


def handle_led_on(client: mqtt.Client, payload: dict[str, Any]) -> None:
    # GPIO code will be added later.
    publish_status(client, {
        "status": "ok",
        "action": "led_on",
        "message": "LED ON placeholder. GPIO not enabled yet.",
        "received_request_id": payload.get("request_id")
    })


def handle_led_off(client: mqtt.Client, payload: dict[str, Any]) -> None:
    # GPIO code will be added later.
    publish_status(client, {
        "status": "ok",
        "action": "led_off",
        "message": "LED OFF placeholder. GPIO not enabled yet.",
        "received_request_id": payload.get("request_id")
    })


def handle_emergency_stop(client: mqtt.Client, payload: dict[str, Any]) -> None:
    # Motor stop code will be added later.
    publish_event(client, {
        "event": "emergency_stop",
        "severity": "critical",
        "message": "Emergency stop received. Motors would stop here.",
        "received_request_id": payload.get("request_id")
    })


def handle_command(client: mqtt.Client, payload: dict[str, Any]) -> None:
    action = payload.get("action")
    capability = payload.get("capability")

    if action == "status" or capability in ["device.status", "robot.status"]:
        handle_status(client, payload)
        return

    if action == "led_on":
        handle_led_on(client, payload)
        return

    if action == "led_off":
        handle_led_off(client, payload)
        return

    if action == "stop_all" or capability == "robot.emergency_stop":
        handle_emergency_stop(client, payload)
        return

    publish_status(client, {
        "status": "error",
        "message": f"Unknown action: {action}",
        "payload": payload
    })


def on_connect(client: mqtt.Client, userdata, flags, rc):
    client.subscribe(COMMAND_TOPIC)

    publish_status(client, {
        "status": "connected",
        "message": f"Subscribed to {COMMAND_TOPIC}"
    })


def on_message(client: mqtt.Client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())
        handle_command(client, payload)
    except Exception as exc:
        publish_status(client, {
            "status": "error",
            "message": str(exc),
            "raw_payload": msg.payload.decode(errors="replace")
        })


def main():
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message

    print(f"Connecting to MQTT broker {MQTT_BROKER}:{MQTT_PORT}")
    print(f"Listening on topic: {COMMAND_TOPIC}")

    client.connect(MQTT_BROKER, MQTT_PORT, 60)
    client.loop_forever()


if __name__ == "__main__":
    main()

