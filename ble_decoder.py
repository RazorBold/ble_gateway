"""
LANSITEC Gateway - Unified Uplink Decoder
==========================================
Mendukung semua message type:
  0x1x = Registration
  0x2x = Heartbeat
  0x6x = Device Parameter Report
  0x7x = BLE Device Message (scan result)
"""

import json
from typing import Dict, Any, Tuple, Optional


# ══════════════════════════════════════════════════════════
#  ENTRY POINT UTAMA
# ══════════════════════════════════════════════════════════

def decode_payload(hex_string: str) -> Dict[str, Any]:
    """
    Decode semua jenis payload LANSITEC gateway dari hex string.
    Dispatch ke decoder yang sesuai berdasarkan high nibble byte pertama.

    Returns dict hasil decode, selalu punya key 'type' dan 'name'.
    """
    hex_clean = hex_string.replace(" ", "").strip().upper()
    if len(hex_clean) % 2 != 0:
        raise ValueError(f"Panjang hex ganjil: {len(hex_clean)} chars")

    data = bytes.fromhex(hex_clean)
    if len(data) < 1:
        raise ValueError("Payload kosong")

    type_byte = data[0]
    msg_type  = (type_byte >> 4) & 0x0F   # high nibble
    sub_type  = type_byte & 0x0F           # low nibble

    if msg_type == 0x1:
        return _decode_registration(data, sub_type)
    elif msg_type == 0x2:
        return _decode_heartbeat(data, sub_type)
    elif msg_type == 0x6:
        return _decode_device_parameter_report(data, sub_type)
    elif msg_type == 0x7:
        return _decode_ble_device_message(data, sub_type)
    else:
        return {
            "type": msg_type, "name": "Unknown",
            "raw_hex": hex_clean,
            "error": f"Message type 0x{msg_type:X} tidak dikenali"
        }


# Alias agar kompatibel dengan kode lama
def decode_ble_payload_field(hex_string: str) -> Optional[Dict[str, Any]]:
    """Wrapper aman, return None jika error (untuk MQTT handler)."""
    try:
        return decode_payload(hex_string)
    except Exception as exc:
        print(f"[Decoder Error] {exc}")
        return None


# ══════════════════════════════════════════════════════════
#  TYPE 0x1 — REGISTRATION
# ══════════════════════════════════════════════════════════

def _decode_registration(data: bytes, _) -> Dict[str, Any]:
    idx = 1
    state           = _parse_state_bytes(data[idx:idx+4]); idx += 4
    idx            += 1                                                          # RFU
    hb_period       = int.from_bytes(data[idx:idx+2], byteorder='big'); idx += 2
    idx            += 6                                                          # RFU
    ble_dri         = int.from_bytes(data[idx:idx+2], byteorder='big'); idx += 2
    ble_rx_duration = data[idx]; idx += 1
    sw_raw          = int.from_bytes(data[idx:idx+2], byteorder='big'); idx += 2
    sw_version      = f"{(sw_raw >> 8)}.{sw_raw & 0xFF:02d}"
    imsi_raw        = data[idx:idx+8]; idx += 8
    imsi            = _decode_bcd_imsi(imsi_raw)
    message_id      = int.from_bytes(data[idx:idx+2], byteorder='big')
    return {
        "type": 1, "name": "Registration",
        "state": state,
        "heartbeat_period_seconds": hb_period * 30,
        "ble_report_interval_seconds": ble_dri * 5,
        "ble_rx_duration_seconds": ble_rx_duration,
        "software_version": sw_version,
        "imsi": imsi,
        "message_id": message_id,
    }


# ══════════════════════════════════════════════════════════
#  TYPE 0x2 — HEARTBEAT
# ══════════════════════════════════════════════════════════

def _decode_heartbeat(data: bytes, _) -> Dict[str, Any]:
    idx              = 1
    state            = _parse_state_bytes(data[idx:idx+4]); idx += 4
    battery_voltage  = data[idx] * 0.1; idx += 1
    battery_level    = data[idx]; idx += 1
    ble_rx_count     = data[idx]; idx += 1
    idx             += 1                                                          # RFU
    temperature      = int.from_bytes(data[idx:idx+2], byteorder='big', signed=True); idx += 2
    idx             += 4                                                          # RFU
    charge_duration  = int.from_bytes(data[idx:idx+2], byteorder='big'); idx += 2
    message_id       = int.from_bytes(data[idx:idx+2], byteorder='big')
    return {
        "type": 2, "name": "Heartbeat",
        "state": state,
        "battery_voltage_V": battery_voltage,
        "battery_percent": battery_level,
        "ble_rx_count_in_period": ble_rx_count,
        "temperature_C": temperature,
        "charge_duration_seconds": charge_duration,
        "message_id": message_id,
    }


# ══════════════════════════════════════════════════════════
#  TYPE 0x6 — DEVICE PARAMETER REPORT
# ══════════════════════════════════════════════════════════

def _decode_device_parameter_report(data: bytes, _) -> Dict[str, Any]:
    result = {"type": 6, "name": "Device Parameter Report", "parameters": [], "message_id": None}
    idx = 1
    while idx <= len(data) - 2:
        if idx == len(data) - 2:
            result["message_id"] = int.from_bytes(data[idx:idx+2], byteorder='big')
            break
        param_type = data[idx]; idx += 1
        if param_type == 0x00:
            val = int.from_bytes(data[idx:idx+2], byteorder='big')
            value = f"{(val >> 8)}.{val & 0xFF:02d}"; idx += 2
        elif param_type == 0x01:
            val = int.from_bytes(data[idx:idx+2], byteorder='big')
            value = f"{val * 30} seconds"; idx += 2
        elif param_type == 0x04:
            val = int.from_bytes(data[idx:idx+2], byteorder='big')
            value = f"{val * 5} seconds"; idx += 2
        elif param_type == 0x07:
            value = f"{data[idx]} seconds"; idx += 1
        elif param_type == 0x10:
            value, idx = _parse_device_report_rule(data, idx)
        elif param_type == 0x29:
            value = "Enabled" if data[idx] else "Disabled"; idx += 1
        elif param_type == 0x2B:
            value = "Enabled" if data[idx] else "Disabled"; idx += 1
        else:
            value = int.from_bytes(data[idx:idx+2], byteorder='big'); idx += 2
        result["parameters"].append({"parameter_type": param_type, "value": value})
    return result


def _parse_device_report_rule(data: bytes, start_idx: int) -> Tuple[Dict[str, Any], int]:
    idx = start_idx
    device_type_qty = data[idx]; idx += 1
    devices = []
    for _ in range(device_type_qty):
        payload_byte   = data[idx]; idx += 1
        device_type_id = (payload_byte >> 4) & 0x0F
        total_blocks   = payload_byte & 0x0F
        blocks = []
        for __ in range(total_blocks):
            rule_type  = data[idx]; idx += 1
            start_addr = data[idx]; idx += 1
            end_addr   = data[idx]; idx += 1
            block = {"rule_type": rule_type, "start": start_addr, "end": end_addr}
            if rule_type == 0x01:
                length = end_addr - start_addr + 1
                block["filter_value"] = data[idx:idx+length].hex().upper()
                idx += length
            blocks.append(block)
        devices.append({"device_type_id": device_type_id, "blocks": blocks})
    return {"device_type_quantity": device_type_qty, "devices": devices}, idx


# ══════════════════════════════════════════════════════════
#  TYPE 0x7 — BLE DEVICE MESSAGE (scan result)
# ══════════════════════════════════════════════════════════

SN_LEN      = 2   # SN selalu 2 bytes
RECORD_SIZE = 3   # SN(2) + RSSI(1)

def _decode_ble_device_message(data: bytes, rule_type: int) -> Dict[str, Any]:
    """
    Decode BLE Device Message (type byte high nibble = 7).

    Format:
      [1 byte Type] [1 byte DevCount] [N x (2 bytes SN + 1 byte RSSI)] [sisa = RFU]

    Contoh: 710133FABA0000000000
      71 = type (device_type=7, rule_type=1)
      01 = 1 device
      33FA = SN, BA = RSSI → -70 dBm
      0000000000 = RFU
    """
    dev_count     = data[1]
    body          = data[2:]
    devices_bytes = RECORD_SIZE * dev_count
    devices_area  = body[:devices_bytes]
    rfu_bytes     = body[devices_bytes:]

    result = {
        "type": 7, "name": "BLE Device Message",
        "raw_hex": data.hex().upper(),
        "device_type": 7,
        "rule_type": rule_type,
        "device_count": dev_count,
        "devices": [],
        "rfu_hex": rfu_bytes.hex().upper() if rfu_bytes else None,
        "errors": [],
    }

    if dev_count == 0:
        result["errors"].append("Device count = 0")
        return result

    if len(devices_area) < devices_bytes:
        result["errors"].append(
            f"Data tidak cukup: butuh {devices_bytes} bytes, tersedia {len(devices_area)}"
        )
        return result

    offset = 0
    for i in range(dev_count):
        sn_bytes = devices_area[offset: offset + SN_LEN]
        rssi_raw = devices_area[offset + SN_LEN]
        rssi_dbm = rssi_raw - 256
        offset  += RECORD_SIZE
        result["devices"].append({
            "index"   : i + 1,
            "sn"      : sn_bytes.hex().upper(),
            "rssi_raw": f"0x{rssi_raw:02X}",
            "rssi_dbm": rssi_dbm,
        })

    return result


# ══════════════════════════════════════════════════════════
#  HELPER
# ══════════════════════════════════════════════════════════

def _parse_state_bytes(state_bytes: bytes) -> Dict[str, Any]:
    state_int = int.from_bytes(state_bytes, byteorder='big')
    return {
        "rssi_sort_enable"    : (state_int >> 25) & 1,
        "ble_receiving_enable": (state_int >> 23) & 1,
        "raw_hex"             : state_bytes.hex().upper(),
    }


def _decode_bcd_imsi(imsi_bytes: bytes) -> str:
    digits = []
    for b in imsi_bytes:
        high, low = (b >> 4) & 0x0F, b & 0x0F
        if high <= 9: digits.append(str(high))
        else: break
        if low  <= 9: digits.append(str(low))
        else: break
    return ''.join(digits)


# ══════════════════════════════════════════════════════════
#  PRETTY PRINT
# ══════════════════════════════════════════════════════════

def print_decoded(result: Dict[str, Any]) -> None:
    """Cetak hasil decode ke console dengan format yang mudah dibaca."""
    msg_type = result.get("type")
    name     = result.get("name", "Unknown")

    print(f"\n{'='*55}")
    print(f"  Message Type : {msg_type} - {name}")
    print(f"{'='*55}")

    if msg_type == 1:          # Registration
        _print_registration(result)
    elif msg_type == 2:        # Heartbeat
        _print_heartbeat(result)
    elif msg_type == 6:        # Device Parameter Report
        _print_device_param(result)
    elif msg_type == 7:        # BLE Device Message
        _print_ble_message(result)
    else:
        print(json.dumps(result, indent=2))

    print(f"{'='*55}")


def _print_registration(r):
    s = r["state"]
    print(f"  📡 State:")
    print(f"     • BLE Receiving  : {'Enabled' if s['ble_receiving_enable'] else 'Disabled'}")
    print(f"     • RSSI Sort      : {'Enabled' if s['rssi_sort_enable'] else 'Disabled'}")
    print(f"  ⏱️  Heartbeat Period : {r['heartbeat_period_seconds']} seconds")
    print(f"  📤 BLE Report Intvl: {r['ble_report_interval_seconds']} seconds")
    print(f"  🕒 BLE Rx Duration : {r['ble_rx_duration_seconds']} seconds")
    print(f"  🔧 Software Version: {r['software_version']}")
    print(f"  📇 IMSI            : {r['imsi']}")
    print(f"  🆔 Message ID      : {r['message_id']}")


def _print_heartbeat(r):
    s = r["state"]
    print(f"  📡 State:")
    print(f"     • BLE Receiving  : {'Enabled' if s['ble_receiving_enable'] else 'Disabled'}")
    print(f"     • RSSI Sort      : {'Enabled' if s['rssi_sort_enable'] else 'Disabled'}")
    print(f"  🔋 Battery Voltage : {r['battery_voltage_V']:.1f} V")
    print(f"  📊 Battery Level   : {r['battery_percent']}%")
    print(f"  📶 BLE Rx Count    : {r['ble_rx_count_in_period']} times")
    print(f"  🌡️  Temperature     : {r['temperature_C']} °C")
    print(f"  ⚡ Charge Duration : {r['charge_duration_seconds']} seconds")
    print(f"  🆔 Message ID      : {r['message_id']}")


def _print_device_param(r):
    PARAM_NAMES = {
        0x00: "Software Version", 0x01: "Heartbeat Period",
        0x04: "Device Report Interval", 0x07: "BLE Rx Duration",
        0x10: "Device Report Rule", 0x29: "BLE Enable", 0x2B: "RSSI Sort Enable",
    }
    print(f"  📦 Parameters:")
    for p in r["parameters"]:
        pname = PARAM_NAMES.get(p["parameter_type"], f"Unknown(0x{p['parameter_type']:02X})")
        val   = p["value"]
        print(f"     • {pname}:")
        if isinstance(val, dict) and "devices" in val:
            for dev in val["devices"]:
                print(f"         Device Type {dev['device_type_id']}:")
                for blk in dev["blocks"]:
                    rule_desc = {1:"Filter", 2:"Data", 3:"MAC"}.get(blk["rule_type"], "?")
                    addr = f"bytes {blk['start']}-{blk['end']}"
                    if blk["rule_type"] == 1:
                        print(f"           - {rule_desc}: {addr} = {blk['filter_value']}")
                    else:
                        print(f"           - {rule_desc}: {addr}")
        else:
            print(f"         {val}")
    print(f"  🆔 Message ID      : {r['message_id']}")


def _print_ble_message(r):
    print(f"  Raw Hex      : {r['raw_hex']}")
    print(f"  Rule Type    : {r['rule_type']}")
    print(f"  Device Count : {r['device_count']}")
    if r.get("rfu_hex"):
        print(f"  RFU          : {r['rfu_hex']}")
    print(f"  {'-'*45}")
    for dev in r["devices"]:
        print(f"  [Device #{dev['index']}]")
        print(f"    SN   : {dev['sn']}")
        print(f"    RSSI : {dev['rssi_raw']} → {dev['rssi_dbm']} dBm")
        print()
    if r.get("errors"):
        for err in r["errors"]:
            print(f"  ⚠  {err}")


# ══════════════════════════════════════════════════════════
#  TEST LANGSUNG
# ══════════════════════════════════════════════════════════

if __name__ == "__main__":
    test_cases = [
        # BLE Device Message (type 7)
        ("710133FABA0000000000",                                                          "BLE - 1 device"),
        ("710233FAB33FBB200000",                                                          "BLE - 2 devices"),
        # Registration (type 1)
        ("10 02800000 00 0078 000000000000 003C 08 0100 460004777770001F 0001 00000000", "Registration"),
        # Heartbeat (type 2)
        ("20 02800000 20 0B 01 00 0023 00000000 0000 0001 00000000",                    "Heartbeat"),
        # Device Parameter Report (type 6)
        ("60 04 003C 0001",                                                              "Param Report (simple)"),
        ("60 10 01 17 01 0001 0201 01 0404 FF 01 0918 F2A52D43E0AB489CB64C4A8300146720 02 0203 02 0508 02 191A 02 1D1D 0001",
                                                                                         "Param Report (with rule)"),
    ]

    for hex_str, desc in test_cases:
        print(f"\n📄 {desc}")
        result = decode_payload(hex_str)
        print_decoded(result)
