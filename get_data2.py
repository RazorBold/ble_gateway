"""
MQTT Listener - LANSITEC BLE Gateway
======================================
Host  : 36.92.47.218
Port  : 14583
Topic : MKGW3/441d64c99fc8/send
"""

import json
import time
import sys
from datetime import datetime

import paho.mqtt.client as mqtt

# ─────────────────────────────────────────────
#  Konfigurasi koneksi
# ─────────────────────────────────────────────
BROKER_HOST = "36.92.47.218"
BROKER_PORT = 14583
TOPIC       = "/MKGW3/441d64c99fc8/send"
CLIENT_ID   = f"ble_listener_{int(time.time())}"

RECONNECT_DELAY = 5  # detik sebelum reconnect


# ─────────────────────────────────────────────
#  Callback MQTT
# ─────────────────────────────────────────────

def on_connect(client, userdata, flags, rc):
    status_map = {
        0: "✅ Terhubung ke broker",
        1: "❌ Versi protokol ditolak",
        2: "❌ Client ID tidak valid",
        3: "❌ Broker tidak tersedia",
        4: "❌ Username / password salah",
        5: "❌ Tidak diotorisasi",
    }
    msg = status_map.get(rc, f"❌ Error tidak dikenal (rc={rc})")
    ts  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n[{ts}] {msg}")

    if rc == 0:
        client.subscribe(TOPIC, qos=1)
        print(f"  📡 Subscribe ke topic : {TOPIC}")
        print(f"  🔌 Broker             : {BROKER_HOST}:{BROKER_PORT}")
    else:
        print(f"  ⚠  Akan mencoba reconnect dalam {RECONNECT_DELAY} detik...")


def on_disconnect(client, userdata, rc):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if rc == 0:
        print(f"\n[{ts}] 🔌 Disconnected secara bersih.")
    else:
        print(f"\n[{ts}] ⚠  Koneksi terputus (rc={rc}). Reconnecting...")


def on_subscribe(client, userdata, mid, granted_qos):
    print(f"  ✔  Subscribe berhasil (QoS={granted_qos})\n")


def on_message(client, userdata, msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n{'━'*55}")
    print(f"  📥 Pesan diterima : {ts}")
    print(f"  📌 Topic          : {msg.topic}")

    try:
        payload_str = msg.payload.decode("utf-8")
        payload     = json.loads(payload_str)

        print(f"\n  📄 Data JSON:")
        print(json.dumps(payload, indent=4, ensure_ascii=False))

    except json.JSONDecodeError:
        print(f"\n  ⚠  Payload bukan JSON:")
        print(f"     {msg.payload.decode('utf-8', errors='replace')}")
    except Exception as exc:
        print(f"\n  ⚠  Error: {exc}")
        print(f"     Raw: {msg.payload}")


# ─────────────────────────────────────────────
#  Main
# ─────────────────────────────────────────────

def main():
    print("=" * 55)
    print("  🛰  LANSITEC BLE Gateway MQTT Listener")
    print("=" * 55)
    print(f"  Broker : {BROKER_HOST}:{BROKER_PORT}")
    print(f"  Topic  : {TOPIC}")
    print("  Tekan Ctrl+C untuk berhenti")
    print("=" * 55)

    client = mqtt.Client(client_id=CLIENT_ID, clean_session=True)
    client.on_connect    = on_connect
    client.on_disconnect = on_disconnect
    client.on_subscribe  = on_subscribe
    client.on_message    = on_message

    client.reconnect_delay_set(min_delay=RECONNECT_DELAY, max_delay=60)

    try:
        client.connect(BROKER_HOST, BROKER_PORT, keepalive=60)
    except Exception as exc:
        print(f"\n❌ Gagal terhubung: {exc}")
        sys.exit(1)

    try:
        client.loop_forever()
    except KeyboardInterrupt:
        print("\n\n🛑 Dihentikan oleh pengguna.")
        client.disconnect()


if __name__ == "__main__":
    main()
