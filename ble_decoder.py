from typing import Optional

"""
BLE Device Message Decoder - LANSITEC Gateway Protocol
Berdasarkan dokumentasi Section 5.5 BLE Device Message

Format:
  [1 byte Type] [1 byte Dev Number] [N x (Data + 1 byte RSSI)] [5 bytes RFU]

Type Byte:
  - Bit 7-4 : Message Type  (nibble atas)
  - Bit 3-0 : Rule Type     (nibble bawah, 0x1–0x3)

Device Number Byte:
  - Bit 7-0 : Jumlah device yang dilaporkan (0x01–0xFF)

Per Device (berulang sejumlah Dev Number):
  - Rule Type 1 : 7 bytes Data (6 bytes MAC + 1 byte extra)  + 1 byte RSSI
  - Rule Type 2 : 8 bytes Data (6 bytes MAC + 2 bytes extra) + 1 byte RSSI
  - Rule Type 3 : 7 bytes Data (3 bytes MAC prefix + 4 bytes payload) + 1 byte RSSI

RSSI Real = byte_value - 256  (unit: dBm)

Contoh 1: 71 03 061A4C000215AABB B3 061A4C000215AABC B4 061A4C000215AABD B5
Contoh 2: 73 01 648216 0010030A C2
"""


# ──────────────────────────────────────────────
# Ukuran data per Rule Type (bytes, TANPA RSSI)
# ──────────────────────────────────────────────
RULE_TYPE_DATA_LEN = {
    1: 7,   # 6 bytes MAC penuh + 1 byte extra
    2: 8,   # 6 bytes MAC penuh + 2 bytes extra
    3: 7,   # 3 bytes MAC prefix + 4 bytes payload
}


def rssi_to_dbm(raw_byte: int) -> int:
    """Konversi raw RSSI byte ke nilai dBm (signed)."""
    return raw_byte - 256


def decode_mac(mac_bytes: bytes) -> str:
    """Format bytes jadi string MAC address."""
    return ":".join(f"{b:02X}" for b in mac_bytes)


def decode_ble_message(hex_string: str) -> dict:
    """
    Decode hex payload BLE Device Message dari LANSITEC gateway.

    Args:
        hex_string: String hex payload (boleh ada spasi atau tidak).
                    Contoh: "71 03 061A4C000215AABB B3 ..."
                         atau "710306..."

    Returns:
        dict berisi hasil decode lengkap.
    """
    # Bersihkan spasi
    hex_clean = hex_string.replace(" ", "").upper()

    if len(hex_clean) % 2 != 0:
        raise ValueError(f"Panjang hex ganjil: {len(hex_clean)} karakter")

    data = bytes.fromhex(hex_clean)

    if len(data) < 2:
        raise ValueError("Payload terlalu pendek (minimal 2 byte)")

    # ── Byte 0: Type ──────────────────────────────────────
    type_byte   = data[0]
    msg_type    = (type_byte >> 4) & 0x0F   # Bit 7-4
    rule_type   = type_byte & 0x0F           # Bit 3-0

    # ── Byte 1: Device Number ─────────────────────────────
    dev_count = data[1]

    result = {
        "raw_hex": hex_clean,
        "type_byte": f"0x{type_byte:02X}",
        "message_type": msg_type,
        "rule_type": rule_type,
        "device_count": dev_count,
        "devices": [],
        "errors": [],
    }

    # Ukuran data per device untuk rule_type ini
    data_len = RULE_TYPE_DATA_LEN.get(rule_type)
    if data_len is None:
        result["errors"].append(
            f"Rule type {rule_type} tidak dikenali (hanya 1, 2, 3)"
        )
        return result

    record_size = data_len + 1  # data + 1 byte RSSI

    # ── Parse setiap device ───────────────────────────────
    offset = 2  # Mulai setelah Type + Dev Number
    for i in range(dev_count):
        if offset + record_size > len(data):
            result["errors"].append(
                f"Data habis saat parsing device ke-{i + 1} "
                f"(offset={offset}, data_len={len(data)})"
            )
            break

        dev_data_bytes = data[offset: offset + data_len]
        rssi_raw       = data[offset + data_len]
        rssi_dbm       = rssi_to_dbm(rssi_raw)
        offset        += record_size

        device_info = {
            "index": i + 1,
            "raw_data_hex": dev_data_bytes.hex().upper(),
            "rssi_raw": f"0x{rssi_raw:02X}",
            "rssi_dbm": rssi_dbm,
        }

        # ── Decode berdasarkan Rule Type ──────────────────
        if rule_type == 1:
            # Rule 1: 6 bytes MAC penuh + 1 byte extra
            mac_bytes = dev_data_bytes[:6]
            extra     = dev_data_bytes[6:]
            device_info["mac_address"] = decode_mac(mac_bytes)
            device_info["extra_data"] = extra.hex().upper()

        elif rule_type == 2:
            # Rule 2: 6 bytes MAC penuh + 2 bytes extra
            mac_bytes = dev_data_bytes[:6]
            extra     = dev_data_bytes[6:]
            device_info["mac_address"] = decode_mac(mac_bytes)
            device_info["extra_data"] = extra.hex().upper()

        elif rule_type == 3:
            # Rule 3: 3 bytes MAC prefix + 4 bytes payload
            mac_prefix  = dev_data_bytes[:3]
            payload     = dev_data_bytes[3:]
            device_info["mac_prefix"] = decode_mac(mac_prefix)
            device_info["payload_hex"] = payload.hex().upper()
            device_info["payload_int"] = int.from_bytes(payload, byteorder="big")

        result["devices"].append(device_info)

    # Sisa bytes setelah semua device (RFU area)
    rfu_bytes = data[offset:]
    if rfu_bytes:
        result["rfu_hex"] = rfu_bytes.hex().upper()

    return result


def print_decoded(result: dict) -> None:
    """Cetak hasil decode ke console dengan format yang mudah dibaca."""
    print("=" * 60)
    print("  BLE DEVICE MESSAGE DECODER")
    print("=" * 60)
    print(f"  Raw Hex      : {result['raw_hex']}")
    print(f"  Type Byte    : {result['type_byte']}")
    print(f"  Message Type : {result['message_type']}")
    print(f"  Rule Type    : {result['rule_type']}")
    print(f"  Device Count : {result['device_count']}")
    print("-" * 60)

    for dev in result["devices"]:
        print(f"  [Device #{dev['index']}]")
        print(f"    Raw Data  : {dev['raw_data_hex']}")
        if "mac_address" in dev:
            print(f"    MAC       : {dev['mac_address']}")
        if "mac_prefix" in dev:
            print(f"    MAC Prefix: {dev['mac_prefix']}")
        if "extra_data" in dev:
            print(f"    Extra Data: {dev['extra_data']}")
        if "payload_hex" in dev:
            print(f"    Payload   : {dev['payload_hex']}  ({dev['payload_int']})")
        print(f"    RSSI      : {dev['rssi_raw']} → {dev['rssi_dbm']} dBm")
        print()

    if result.get("rfu_hex"):
        print(f"  RFU Bytes : {result['rfu_hex']}")

    if result.get("errors"):
        print("  ERRORS:")
        for err in result["errors"]:
            print(f"    ⚠  {err}")

    print("=" * 60)


# ──────────────────────────────────────────────
# Fungsi helper untuk integrasi ke MQTT handler
# ──────────────────────────────────────────────
def decode_ble_payload_field(hex_string: str) -> Optional[dict]:
    """
    Wrapper aman untuk dipanggil di on_message MQTT.
    Mengembalikan None jika terjadi error.
    """
    try:
        return decode_ble_message(hex_string)
    except Exception as exc:
        print(f"[BLE Decoder Error] {exc}")
        return None


# ──────────────────────────────────────────────
# Test / demo langsung
# ──────────────────────────────────────────────
if __name__ == "__main__":
    test_cases = [
        # Contoh 1 dari dokumentasi (Rule Type 1, 3 devices)
        "71 03 061A4C000215AABB B3 061A4C000215AABC B4 061A4C000215AABD B5",
        # Contoh 2 dari dokumentasi (Rule Type 3, 1 device)
        "73 01 6482160010030A C2",
    ]

    for tc in test_cases:
        result = decode_ble_message(tc)
        print_decoded(result)
        print()
