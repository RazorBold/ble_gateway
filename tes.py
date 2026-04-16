#!/usr/bin/env python3
"""
Lansitec BLE Gateway - Downlink Message Generator
Menghasilkan hex string untuk dikirim ke MQTT topic: lansitec/sub/IMEI
"""

def encode_gateway_config(parameters, message_id):
    """
    Encode Gateway Configuration (Type 0xA)
    parameters: list of tuples (param_type, value)
        param_type:
          0x01 -> HB Period (value: int seconds, min 30s)
          0x03 -> GNSS Position Report Interval (value: int seconds, 0=OFF)
          0x04 -> Device Report Interval (value: int seconds, 0=OFF)
          0x07 -> BLE Rx Duration (value: int seconds, 0-10, 0=continuous)
          0x10 -> Device Report Rule (value: dict, advanced)
          0x29 -> BLE Enable (value: bool)
          0x2B -> RSSI Sort Enable (value: bool)
          0x7F -> Beacon Buzzer Control (value: tuple (major, minor))
    """
    payload = bytearray()
    payload.append(0xA0)  # Type 0xA, lower nibble RFU=0

    for param_type, val in parameters:
        payload.append(param_type)
        if param_type == 0x01:  # HB Period
            period_30s = max(1, val // 30)
            payload.extend(period_30s.to_bytes(2, 'big'))
        elif param_type == 0x03:  # GNSS Position Report Interval
            interval_5s = max(0, val // 5)
            payload.extend(interval_5s.to_bytes(2, 'big'))
        elif param_type == 0x04:  # Device Report Interval
            interval_5s = max(0, val // 5)
            payload.extend(interval_5s.to_bytes(2, 'big'))
        elif param_type == 0x07:  # BLE Rx Duration
            if val < 0 or val > 10:
                raise ValueError("BLE Rx Duration must be 0-10 seconds")
            payload.append(val & 0xFF)
        elif param_type == 0x10:  # Device Report Rule
            rule_bytes = encode_device_report_rule(val)
            payload.extend(rule_bytes)
        elif param_type == 0x29 or param_type == 0x2B:
            payload.append(0x01 if val else 0x00)
        elif param_type == 0x7F:  # Beacon Buzzer Control
            major, minor = val
            payload.extend(major.to_bytes(2, 'big'))
            payload.extend(minor.to_bytes(2, 'big'))
        else:
            raise ValueError(f"Unsupported parameter type: 0x{param_type:02X}")

    payload.extend(message_id.to_bytes(2, 'big'))
    return payload.hex().upper()

def encode_device_report_rule(rule_dict):
    """Encode Device Report Rule (0x10) - untuk advanced use"""
    result = bytearray()
    result.append(rule_dict["device_type_quantity"])
    for dev in rule_dict["devices"]:
        device_type_id = dev["device_type_id"]
        total_blocks = len(dev["blocks"])
        payload_byte = (device_type_id << 4) | total_blocks
        result.append(payload_byte)
        for blk in dev["blocks"]:
            result.append(blk["rule_type"])
            result.append(blk["start"])
            result.append(blk["end"])
            if blk["rule_type"] == 0x01:
                filter_bytes = bytes.fromhex(blk["filter_value"])
                result.extend(filter_bytes)
    return bytes(result)

def encode_query_config(parameter_types, message_id):
    """Encode Query Gateway Configuration (Type 0xB)"""
    payload = bytearray()
    payload.append(0xB0)
    for pt in parameter_types:
        payload.append(pt)
    payload.extend(message_id.to_bytes(2, 'big'))
    return payload.hex().upper()

def format_hex_pretty(hex_str):
    """Format hex menjadi tampilan seperti contoh: A0 7F 3000 1378 0004
    (mengelompokkan 2 digit, tapi untuk Major/Minor 4 digit tetap rapat)
    """
    # Pisahkan per 2 digit
    pairs = [hex_str[i:i+2] for i in range(0, len(hex_str), 2)]
    # Deteksi pola untuk Beacon Buzzer (0x7F) -> setelah 0x7F ada 4 byte (major+minor)
    # Cari index 0x7F
    result = []
    i = 0
    while i < len(pairs):
        if pairs[i] == '7F' and i+1 < len(pairs) and pairs[i-1] == 'A0':
            # Ini parameter 0x7F, ambil major (2 byte) dan minor (2 byte)
            major = pairs[i+1] + pairs[i+2]  # 4 digit
            minor = pairs[i+3] + pairs[i+4]  # 4 digit
            result.append(pairs[i])     # '7F'
            result.append(major)        # '3000'
            result.append(minor)        # '1378'
            i += 5
        else:
            result.append(pairs[i])
            i += 1
    return ' '.join(result)

def print_menu():
    print("\n" + "="*50)
    print("  LANSITEC BLE GATEWAY - DOWNLINK GENERATOR")
    print("="*50)
    print("Pilih jenis pesan:")
    print("1. Gateway Configuration (Type 0xA)")
    print("2. Query Gateway Configuration (Type 0xB)")
    print("0. Keluar")
    print("-"*50)

def param_menu():
    print("\nParameter yang tersedia untuk Gateway Configuration:")
    print("  1. Heartbeat Period (0x01) - satuan detik, min 30")
    print("  2. GNSS Position Report Interval (0x03) - detik, 0=OFF")
    print("  3. Device Report Interval (0x04) - detik, 0=OFF")
    print("  4. BLE Receiving Duration (0x07) - 0-10 detik, 0=continuous")
    print("  5. BLE Enable (0x29) - 0=Disable, 1=Enable")
    print("  6. RSSI Sort Enable (0x2B) - 0=Disable, 1=Enable")
    print("  7. Beacon Buzzer Control (0x7F) - masukkan Major dan Minor (hex)")
    print("  0. Selesai menambah parameter")
    print("-"*50)

def get_parameters():
    params = []
    while True:
        param_menu()
        choice = input("Pilih parameter (0-7): ").strip()
        if choice == '0':
            break
        elif choice == '1':
            try:
                sec = int(input("Heartbeat Period (detik, min 30): "))
                if sec < 30:
                    sec = 30
                params.append((0x01, sec))
                print(f"✓ Ditambahkan: HB Period = {sec} detik")
            except:
                print("Input tidak valid!")
        elif choice == '2':
            try:
                sec = int(input("GNSS Position Report Interval (detik, 0=OFF): "))
                params.append((0x03, sec))
                print(f"✓ Ditambahkan: GNSS Interval = {sec} detik")
            except:
                print("Input tidak valid!")
        elif choice == '3':
            try:
                sec = int(input("Device Report Interval (detik, 0=OFF): "))
                params.append((0x04, sec))
                print(f"✓ Ditambahkan: Device Report Interval = {sec} detik")
            except:
                print("Input tidak valid!")
        elif choice == '4':
            try:
                dur = int(input("BLE Rx Duration (0-10 detik, 0=continuous): "))
                if dur < 0 or dur > 10:
                    dur = 0
                params.append((0x07, dur))
                print(f"✓ Ditambahkan: BLE Rx Duration = {dur} detik")
            except:
                print("Input tidak valid!")
        elif choice == '5':
            val = input("BLE Enable (1=Enable, 0=Disable): ")
            enable = (val == '1')
            params.append((0x29, enable))
            print(f"✓ BLE Enable = {'Enabled' if enable else 'Disabled'}")
        elif choice == '6':
            val = input("RSSI Sort Enable (1=Enable, 0=Disable): ")
            enable = (val == '1')
            params.append((0x2B, enable))
            print(f"✓ RSSI Sort Enable = {'Enabled' if enable else 'Disabled'}")
        elif choice == '7':
            try:
                major_hex = input("Major (hex, 2 byte, contoh: 3000): ").strip()
                minor_hex = input("Minor (hex, 2 byte, contoh: 1378): ").strip()
                major = int(major_hex, 16)
                minor = int(minor_hex, 16)
                params.append((0x7F, (major, minor)))
                print(f"✓ Beacon Buzzer: Major=0x{major:04X}, Minor=0x{minor:04X}")
            except:
                print("Input hex tidak valid!")
        else:
            print("Pilihan tidak dikenal")
    return params

def get_query_params():
    param_codes = {
        '1': 0x00, '2': 0x01, '3': 0x03, '4': 0x04,
        '5': 0x07, '6': 0x0E, '7': 0x10, '8': 0x29, '9': 0x2B
    }
    print("\nParameter yang bisa di-query:")
    print("  1. Software Version (0x00)")
    print("  2. Heartbeat Period (0x01)")
    print("  3. GNSS Position Report Interval (0x03)")
    print("  4. Device Report Interval (0x04)")
    print("  5. BLE Receiving Duration (0x07)")
    print("  6. IMSI (0x0E)")
    print("  7. Device Report Rule (0x10)")
    print("  8. BLE Enable (0x29)")
    print("  9. RSSI Sort Enable (0x2B)")
    print("  0. Selesai")
    types = []
    while True:
        ch = input("Pilih nomor (0-9): ").strip()
        if ch == '0':
            break
        elif ch in param_codes:
            pt = param_codes[ch]
            if pt not in types:
                types.append(pt)
                print(f"✓ Ditambahkan: {ch}")
            else:
                print("Sudah ada")
        else:
            print("Pilihan tidak valid")
    return types

def main():
    while True:
        print_menu()
        pilih = input("Pilihan: ").strip()
        if pilih == '0':
            print("Keluar.")
            break
        elif pilih == '1':
            params = get_parameters()
            if not params:
                print("Tidak ada parameter, batal.")
                continue
            try:
                msg_id = int(input("Message ID (1-65535): "))
                if msg_id < 1 or msg_id > 65535:
                    msg_id = 1
            except:
                msg_id = 1
            hex_raw = encode_gateway_config(params, msg_id)
            pretty = format_hex_pretty(hex_raw)
            print("\n" + "="*50)
            print("Hasil Gateway Configuration (hex):")
            print(pretty)
            print("\nSalin string di atas dan kirim ke topic MQTT:")
            print("lansitec/sub/IMEI")
            print("="*50)
        elif pilih == '2':
            types = get_query_params()
            if not types:
                print("Tidak ada parameter, batal.")
                continue
            try:
                msg_id = int(input("Message ID (1-65535): "))
                if msg_id < 1 or msg_id > 65535:
                    msg_id = 1
            except:
                msg_id = 1
            hex_raw = encode_query_config(types, msg_id)
            pretty = ' '.join(hex_raw[i:i+2] for i in range(0, len(hex_raw), 2))
            print("\n" + "="*50)
            print("Hasil Query Gateway Configuration (hex):")
            print(pretty)
            print("\nKirim ke topic: lansitec/sub/IMEI")
            print("="*50)
        else:
            print("Pilihan tidak valid.")

if __name__ == "__main__":
    main()