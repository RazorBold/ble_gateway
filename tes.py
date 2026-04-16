import struct
import json
from typing import Dict, Any, Tuple

def decode_uplink(hex_string: str) -> Dict[str, Any]:
    """Decode uplink message, sama seperti sebelumnya"""
    hex_clean = hex_string.replace(" ", "").strip()
    if len(hex_clean) % 2 != 0:
        raise ValueError("Invalid hex string length")
    data = bytes.fromhex(hex_clean)
    if len(data) < 1:
        raise ValueError("Empty data")
    type_byte = data[0]
    msg_type = (type_byte >> 4) & 0x0F
    rfu_nibble = type_byte & 0x0F
    if msg_type == 0x1:
        return _decode_registration(data, rfu_nibble)
    elif msg_type == 0x2:
        return _decode_heartbeat(data, rfu_nibble)
    elif msg_type == 0x6:
        return _decode_device_parameter_report(data, rfu_nibble)
    else:
        return {"type": msg_type, "error": f"Unsupported message type: {msg_type}", "raw": hex_clean}

def _parse_state_bytes(state_bytes: bytes) -> Dict[str, Any]:
    state_int = int.from_bytes(state_bytes, byteorder='big')
    return {
        "rssi_sort_enable": (state_int >> 25) & 1,
        "ble_receiving_enable": (state_int >> 23) & 1,
        "raw_hex": state_bytes.hex().upper()
    }

def _decode_registration(data: bytes, _) -> Dict[str, Any]:
    idx = 1
    state = _parse_state_bytes(data[idx:idx+4]); idx += 4
    idx += 1  # RFU
    hb_period = int.from_bytes(data[idx:idx+2], byteorder='big'); idx += 2
    idx += 6  # RFU
    ble_dri = int.from_bytes(data[idx:idx+2], byteorder='big'); idx += 2
    ble_rx_duration = data[idx]; idx += 1
    sw_raw = int.from_bytes(data[idx:idx+2], byteorder='big'); idx += 2
    sw_version = f"{(sw_raw >> 8)}.{sw_raw & 0xFF:02d}"
    imsi_raw = data[idx:idx+8]; idx += 8
    imsi = _decode_bcd_imsi(imsi_raw)
    message_id = int.from_bytes(data[idx:idx+2], byteorder='big')
    return {
        "type": 1, "name": "Registration",
        "state": state, "heartbeat_period_seconds": hb_period * 30,
        "ble_report_interval_seconds": ble_dri * 5,
        "ble_rx_duration_seconds": ble_rx_duration,
        "software_version": sw_version, "imsi": imsi, "message_id": message_id
    }

def _decode_heartbeat(data: bytes, _) -> Dict[str, Any]:
    idx = 1
    state = _parse_state_bytes(data[idx:idx+4]); idx += 4
    battery_voltage = data[idx] * 0.1; idx += 1
    battery_level = data[idx]; idx += 1
    ble_rx_count = data[idx]; idx += 1
    idx += 1  # RFU
    temperature = int.from_bytes(data[idx:idx+2], byteorder='big', signed=True); idx += 2
    idx += 4  # RFU
    charge_duration = int.from_bytes(data[idx:idx+2], byteorder='big'); idx += 2
    message_id = int.from_bytes(data[idx:idx+2], byteorder='big')
    return {
        "type": 2, "name": "Heartbeat",
        "state": state, "battery_voltage_V": battery_voltage,
        "battery_percent": battery_level, "ble_rx_count_in_period": ble_rx_count,
        "temperature_C": temperature, "charge_duration_seconds": charge_duration,
        "message_id": message_id
    }

def _decode_device_parameter_report(data: bytes, _) -> Dict[str, Any]:
    result = {"type": 6, "name": "Device Parameter Report", "parameters": [], "message_id": None}
    idx = 1
    while idx <= len(data) - 2:
        if idx == len(data) - 2:
            result["message_id"] = int.from_bytes(data[idx:idx+2], byteorder='big')
            break
        param_type = data[idx]; idx += 1
        if param_type == 0x00:  # Software Version
            val = int.from_bytes(data[idx:idx+2], byteorder='big')
            value = f"{(val >> 8)}.{val & 0xFF:02d}"
            idx += 2
        elif param_type == 0x01:  # HB Period
            val = int.from_bytes(data[idx:idx+2], byteorder='big')
            value = f"{val * 30} seconds"
            idx += 2
        elif param_type == 0x04:  # Device Report Interval
            val = int.from_bytes(data[idx:idx+2], byteorder='big')
            value = f"{val * 5} seconds"
            idx += 2
        elif param_type == 0x07:  # BLE Rx Duration
            value = f"{data[idx]} seconds"
            idx += 1
        elif param_type == 0x10:  # Device Report Rule
            value, idx = _parse_device_report_rule(data, idx)
        elif param_type == 0x29:  # BLE Enable
            value = "Enabled" if data[idx] else "Disabled"
            idx += 1
        elif param_type == 0x2B:  # RSSI Sort Enable
            value = "Enabled" if data[idx] else "Disabled"
            idx += 1
        else:
            # Unknown: skip 2 bytes as fallback
            value = int.from_bytes(data[idx:idx+2], byteorder='big')
            idx += 2
        result["parameters"].append({"parameter_type": param_type, "value": value})
    return result

def _parse_device_report_rule(data: bytes, start_idx: int) -> Tuple[Dict[str, Any], int]:
    idx = start_idx
    device_type_qty = data[idx]; idx += 1
    devices = []
    for _ in range(device_type_qty):
        payload_byte = data[idx]; idx += 1
        device_type_id = (payload_byte >> 4) & 0x0F
        total_blocks = payload_byte & 0x0F
        blocks = []
        for __ in range(total_blocks):
            rule_type = data[idx]; idx += 1
            start_addr = data[idx]; idx += 1
            end_addr = data[idx]; idx += 1
            block = {"rule_type": rule_type, "start": start_addr, "end": end_addr}
            if rule_type == 0x01:  # Filter block
                length = end_addr - start_addr + 1
                filter_val = data[idx:idx+length].hex().upper()
                idx += length
                block["filter_value"] = filter_val
            blocks.append(block)
        devices.append({"device_type_id": device_type_id, "blocks": blocks})
    return {"device_type_quantity": device_type_qty, "devices": devices}, idx

def _decode_bcd_imsi(imsi_bytes: bytes) -> str:
    digits = []
    for b in imsi_bytes:
        high = (b >> 4) & 0x0F
        low = b & 0x0F
        if high <= 9:
            digits.append(str(high))
        else:
            break
        if low <= 9:
            digits.append(str(low))
        else:
            break
    return ''.join(digits)

# ==================== PRETTY PRINT ====================
def pretty_print(result: Dict[str, Any]):
    """Cetak hasil decode dengan format rapi"""
    msg_type = result.get("type")
    name = result.get("name", "Unknown")
    print(f"\n{'='*60}")
    print(f"Message Type: {msg_type} - {name}")
    print('='*60)
    
    if msg_type == 1:  # Registration
        s = result["state"]
        print(f"📡 State:")
        print(f"   • BLE Receiving  : {'Enabled' if s['ble_receiving_enable'] else 'Disabled'}")
        print(f"   • RSSI Sort      : {'Enabled' if s['rssi_sort_enable'] else 'Disabled'}")
        print(f"⏱️ Heartbeat Period : {result['heartbeat_period_seconds']} seconds")
        print(f"📤 BLE Report Intvl: {result['ble_report_interval_seconds']} seconds")
        print(f"🕒 BLE Rx Duration : {result['ble_rx_duration_seconds']} seconds")
        print(f"🔧 Software Version: {result['software_version']}")
        print(f"📇 IMSI            : {result['imsi']}")
        print(f"🆔 Message ID      : {result['message_id']}")
    
    elif msg_type == 2:  # Heartbeat
        s = result["state"]
        print(f"📡 State:")
        print(f"   • BLE Receiving  : {'Enabled' if s['ble_receiving_enable'] else 'Disabled'}")
        print(f"   • RSSI Sort      : {'Enabled' if s['rssi_sort_enable'] else 'Disabled'}")
        print(f"🔋 Battery Voltage : {result['battery_voltage_V']:.1f} V")
        print(f"📊 Battery Level   : {result['battery_percent']}%")
        print(f"📶 BLE Rx Count    : {result['ble_rx_count_in_period']} times")
        print(f"🌡️ Temperature      : {result['temperature_C']} °C")
        print(f"⚡ Charge Duration : {result['charge_duration_seconds']} seconds")
        print(f"🆔 Message ID      : {result['message_id']}")
    
    elif msg_type == 6:  # Device Parameter Report
        print(f"📦 Parameters:")
        for p in result["parameters"]:
            param_name = {
                0x00: "Software Version", 0x01: "Heartbeat Period",
                0x04: "Device Report Interval", 0x07: "BLE Rx Duration",
                0x10: "Device Report Rule", 0x29: "BLE Enable",
                0x2B: "RSSI Sort Enable"
            }.get(p["parameter_type"], f"Unknown(0x{p['parameter_type']:02X})")
            print(f"   • {param_name}:")
            val = p["value"]
            if isinstance(val, dict) and "devices" in val:
                # Cetak aturan device report dengan indentasi
                for dev in val["devices"]:
                    print(f"       Device Type {dev['device_type_id']}:")
                    for blk in dev["blocks"]:
                        rule_desc = {1: "Filter", 2: "Data", 3:"MAC"}.get(blk["rule_type"], "?")
                        addr = f"bytes {blk['start']}-{blk['end']}"
                        if blk["rule_type"] == 1:
                            print(f"         - {rule_desc} block: {addr} = {blk['filter_value']}")
                        else:
                            print(f"         - {rule_desc} block: {addr} (report this range)")
            else:
                print(f"       {val}")
        print(f"🆔 Message ID      : {result['message_id']}")
    else:
        print(json.dumps(result, indent=2))

# ==================== MAIN ====================
if __name__ == "__main__":
    test_cases = [
        ("10 02800000 00 0078 000000000000 003C 08 0100 460004777770001F 0001 00000000", "Registration"),
        ("20 02800000 20 0B 01 00 0023 00000000 0000 0001 00000000", "Heartbeat"),
        ("60 04 003C 0001", "Device Parameter Report (simple)"),
        ("60 10 01 17 01 0001 0201 01 0404 FF 01 0918 F2A52D43E0AB489CB64C4A8300146720 02 0203 02 0508 02 191A 02 1D1D 0001", "Device Parameter Report (with rule)")
    ]
    for hex_str, desc in test_cases:
        print(f"\n📄 Contoh: {desc}")
        decoded = decode_uplink(hex_str)
        pretty_print(decoded)