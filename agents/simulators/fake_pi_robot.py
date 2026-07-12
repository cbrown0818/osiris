import json
import socket
import time
from typing import Any

import paho.mqtt.client as mqtt


DEVICE_ID = "pi_robot_1"
MQTT_BROKER = "localhost"
MQTT_PORT = 1883

COMMAND_TOPIC = f"osiris/{DEVICE_ID}/command"
STATUS_TOPIC = f"osiris/{DEVICE_ID}/status"
EVENT_TOPIC = f"osiris/{DEVICE_ID}/events"


def publish(client: mqtt.Client, topic: str, payload: dict[str, Any]) -> None:
    message = {
        "device_id": DEVICE_ID,
        "hostname": socket.gethostname(),
        "simulated": True,
        "timestamp": time.time(),
        **payload,
    }

    client.publish(topic, json.dumps(message))


def handle_command(client: mqtt.Client, payload: dict[str, Any]) -> None:
    action = payload.get("action")
    capability = payload.get("capability")
    request_id = payload.get("request_id")

    if action == "status" or capability in ["device.status", "robot.status"]:
        publish(client, STATUS_TOPIC, {
            "status": "online",
            "message": "Fake Pi robot is online.",
            "received_request_id": request_id
        })
        return

    if action == "stop_all" or capability == "robot.emergency_stop":
        publish(client, EVENT_TOPIC, {
            "event": "emergency_stop",
            "severity": "critical",
            "message": "Fake emergency stop received. Simulated motors stopped.",
            "received_request_id": request_id
        })
        return

    if action == "led_on":
        publish(client, STATUS_TOPIC, {
            "status": "ok",
            "action": "led_on",
            "message": "Fake LED turned on.",
            "received_request_id": request_id
        })
        return

    if action == "led_off":
        publish(client, STATUS_TOPIC, {
            "status": "ok",
            "action": "led_off",
            "message": "Fake LED turned off.",
            "received_request_id": request_id
        })
        return


    if action in ["move_forward", "move_backward", "turn_left", "turn_right"]:
        params = payload.get("params", {})
        publish(client, EVENT_TOPIC, {
            "event": "robot_movement",
            "severity": "info",
            "action": action,
            "message": f"Fake robot executed {action}.",
            "speed_percent": params.get("speed_percent"),
            "duration_seconds": params.get("duration_seconds"),
            "received_request_id": request_id
        })
        return

    publish(client, STATUS_TOPIC, {
        "status": "error",
        "message": f"Unknown fake device action: {action}",
        "payload": payload
    })


def on_connect(client: mqtt.Client, userdata, flags, rc):
    client.subscribe(COMMAND_TOPIC)

    publish(client, STATUS_TOPIC, {
        "status": "connected",
        "message": f"Fake Pi subscribed to {COMMAND_TOPIC}"
    })


def on_message(client: mqtt.Client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())
        handle_command(client, payload)
    except Exception as exc:
        publish(client, STATUS_TOPIC, {
            "status": "error",
            "message": str(exc),
            "raw_payload": msg.payload.decode(errors="replace")
        })


def main():
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message

    print(f"Fake Pi connecting to MQTT broker {MQTT_BROKER}:{MQTT_PORT}")
    print(f"Listening on {COMMAND_TOPIC}")

    client.connect(MQTT_BROKER, MQTT_PORT, 60)
    client.loop_forever()


if __name__ == "__main__":
    main()
