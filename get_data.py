import paho.mqtt.client as mqtt
import json
from datetime import datetime

from ble_decoder import decode_ble_payload_field, print_decoded, decode_payload

# MQTT Config
MQTT_HOST = "36.92.47.218"
MQTT_PORT = 14583
MQTT_TOPIC = "lansitec/pub/866846063550726"


def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print(f"[{datetime.now()}] Connected to MQTT broker {MQTT_HOST}:{MQTT_PORT}")
        client.subscribe(MQTT_TOPIC)
        print(f"[{datetime.now()}] Subscribed to topic: {MQTT_TOPIC}")
    else:
        print(f"[{datetime.now()}] Failed to connect, return code: {rc}")


def on_message(client, userdata, msg):
    print(f"\n[{datetime.now()}] Message received on topic: {msg.topic}")
    try:
        # Coba parse sebagai JSON dulu
        payload = json.loads(msg.payload.decode("utf-8"))
        print(json.dumps(payload, indent=2))

        # Kalau ada field BLE hex di dalam JSON
        ble_hex = payload.get("ble_msg") or payload.get("bleMSG") or payload.get("data")
        if ble_hex and isinstance(ble_hex, str):
            decoded = decode_ble_payload_field(ble_hex)
            if decoded:
                print_decoded(decoded)

    except (json.JSONDecodeError, UnicodeDecodeError):
        # Payload bukan JSON → coba decode langsung sebagai BLE hex string
        raw_hex = msg.payload.decode("utf-8", errors="ignore").strip()
        print(f"Payload (raw hex): {raw_hex}")
        decoded = decode_ble_payload_field(raw_hex)
        if decoded:
            print_decoded(decoded)


def on_disconnect(client, userdata, rc):
    print(f"[{datetime.now()}] Disconnected from broker (rc={rc})")


def main():
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message
    client.on_disconnect = on_disconnect

    print(f"Connecting to {MQTT_HOST}:{MQTT_PORT} ...")
    client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)

    try:
        client.loop_forever()
    except KeyboardInterrupt:
        print("\nStopped by user.")
        client.disconnect()


if __name__ == "__main__":
    main()
