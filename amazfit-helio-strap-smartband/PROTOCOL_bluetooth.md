# Amazfit Helio Strap — BLE & Cloud Protocol Reference

All findings are based on direct device testing with bleak on macOS (CoreBluetooth).
Device: Amazfit Helio Strap, CoreBluetooth UUID discovered via BT Scan.

---

## 1. GATT Service Map

```
0000180a-0000-1000-8000-00805f9b34fb  Device Information
  00002a23  [read]  System ID
  00002a25  [read]  Serial Number
  00002a27  [read]  Hardware Revision
  00002a28  [read]  Software Revision
  00002a50  [read]  PnP ID
  00002a29  [read]  Manufacturer Name

0000fee0-0000-1000-8000-00805f9b34fb  Anhui Huami (main data service)
  00002a2b  [read, write, notify]  Current Time (BLE standard CT)
  00000016  [write-without-response, notify]  Chunked TX (phone→device)
  00000017  [write-without-response, notify]  Chunked RX (device→phone)
  00000001  [write, notify]  AUTH (key exchange)
  00000002  [notify]  Sensor stream (real-time calories)
  00000004  [write-without-response, notify]  Fetch control (write cmd / read response)
  00000005  [notify]  Fetch data stream
  00000006  [read, write-without-response, notify]  Sensor control (HR enable)
  00000025  [write-without-response, notify]  Unknown

00001530-0000-3512-2118-0009af100700  OTA / Firmware Update
  00001531  [write, notify]
  00001532  [write-without-response]
  00000023  [write-without-response, notify]
  00000024  [write-without-response, notify]

0000180d-0000-1000-8000-00805f9b34fb  Heart Rate Service (BLE standard)
  00002a37  [notify]  HR Measurement  ← WORKING (1/sec with keepalive)
  00002a38  [read]   Body Sensor Location (read not permitted)

0000fee1-0000-1000-8000-00805f9b34fb  Anhui Huami (legacy auth)
  0000fedd  [write]   Legacy auth write  (NOT usable — no notify)
  0000fede  [read]    Legacy auth read   (always returns 0 bytes)

0000180f-0000-1000-8000-00805f9b34fb  Battery Service (BLE standard)
  00002a19  [read, notify]  Battery Level  ← WORKING
```

---

## 2. Authentication — Two Phases

### Phase 1 — Standard Key Auth (0x0001)

Characteristic: `00000001-0000-3512-2118-0009af100700`

#### Step 1 — Send auth key
```
WRITE (response=True): [0x01, 0x00] + auth_key_16_bytes
```
Response notification: `10 01 01 05` → key accepted
(The `05` indicates auth type 5 — bonded device key-only auth)

#### Step 2 — Request challenge
```
WRITE (response=True): [0x02, 0x00]
```
Response notification: `10 02 01` (3 bytes only — no challenge follows)
→ Device is bonded; **no challenge-response needed**.
→ Phase 1 complete.

#### Important
- **Always call `stop_notify()` on 0x0001 after auth** — leaving it subscribed blocks subsequent notify subscriptions on macOS CoreBluetooth.
- Legacy chars 0xFEDD/0xFEDE are **not usable**.

### Phase 2 — ECDH B-163 Auth (endpoint 0x0082 via 0x0016/0x0017)

**Required to unlock all health data** (SpO2, sleep, stress, HRV, activity fetch).
Without this, all fetch type codes except 0x55 return `0x0b` (locked).

Write to `0x0016`, listen on `0x0017`.

#### ECDH Handshake Flow

```
1. Phone generates ECDH keypair on NIST B-163 (sect163r2) curve
2. Phone → Device (endpoint 0x0082): [0x04, 0x02, 0x00, 0x02] + public_key_48bytes
3. Device → Phone (endpoint 0x0082): [0x10, 0x04, 0x01, ...] + random_16bytes + device_pubkey_48bytes
4. Phone computes: shared_secret = ECDH(private_key, device_pubkey)
5. Phone derives: session_key[i] = shared_secret[i+8] XOR auth_key[i]  (i=0..15)
6. Phone derives: enc_seq_nr = uint32_LE(shared_secret[0:4])
7. Phone → Device (endpoint 0x0082): [0x05] + AES_ECB(random, auth_key) + AES_ECB(random, session_key)
8. Device → Phone: [0x10, 0x05, 0x01] = auth SUCCESS
```

#### Key Technical Details

- **Curve**: SECT163R2 (B-163), using Python `cryptography` library or custom `ecdh_b163` module
- **Public key encoding**: 48 bytes = 24 bytes X + 24 bytes Y (little-endian, zero-padded from 21 bytes to 24 bytes)
- **Shared secret**: 24 bytes X-coordinate of shared point (little-endian)
- **Session key derivation**: `shared_secret[i+8] XOR auth_key[i]` for `i` in `0..15`
- **Encryption sequence**: `uint32_LE(shared_secret[0:4])`
- **Confirmation payload**: `[0x05] + AES_ECB_encrypt(device_random, auth_key) + AES_ECB_encrypt(device_random, session_key)` = 33 bytes

#### Response Codes

| Byte 2 | Meaning |
|--------|---------|
| `0x01` | Authentication successful |
| `0x02` | Unknown status (may indicate partial success) |
| `0x25` | Auth key invalid — wrong session key derivation or stale auth key |

#### Auth Key Staleness

After a factory reset or re-pairing with the Zepp app, the device generates a **new auth key**. The old key still passes Phase 1 (basic auth) but Phase 2 (ECDH) fails with `0x25`. Use `./extract_auth_key.sh` to re-extract.

#### Chunked Frame Format (write to 0x0016)

```
byte[0]    0x03  (flags: first+last+ack)
byte[1]    0x03  (command marker)
byte[2]    0x00  (reserved)
byte[3]    handle (increments per frame, wraps at 0xFF)
byte[4]    0x00  (chunk count: 0 = single chunk)
bytes[5:7] payload_length  uint16 LE (excludes header)
bytes[7:9] 0x00 0x00  (padding)
bytes[9:11] endpoint_id  uint16 LE
bytes[11+]  payload
```

#### Chunked Response Format (read from 0x0017)

Same header structure. Parse `endpoint` at bytes[9:11], payload starts at byte[11], length from bytes[5:7].

---

## 3. Real-time Heart Rate (0x2A37)

Characteristic: `00002a37-0000-1000-8000-00805f9b34fb`

Standard BLE Heart Rate Measurement characteristic.
Works **without authentication**, but requires periodic keepalive.

### Keepalive Protocol (discovered via testing)

The device stops sending HR notifications after ~30 seconds unless a keepalive is sent:

```
Every 30 seconds:
  1. Stop notify on 0x2A37
  2. Write [0x15, 0x01, 0x01] to 0x0006 (sensor control)
  3. Start notify on 0x2A37
```

This re-subscribe + sensor control write cycle produces continuous ~1/sec HR readings.

### Packet format
```
byte[0]  flags   (bit 0 = 0 → 8-bit HR; bit 0 = 1 → 16-bit HR)
byte[1]  HR BPM  (if 8-bit)
byte[1:3] HR BPM little-endian (if 16-bit)
```

Example: `00 45` → flags=0x00 (8-bit), HR=69 bpm

---

## 4. Battery Level (0x2A19)

```
READ → single byte: battery percentage (0–100)
```
Works without authentication.

---

## 5. Current Time (0x2A2B)

Characteristic: `00002a2b-0000-1000-8000-00805f9b34fb`

### Read (11 bytes)
```
bytes[0:2]  year      uint16 LE
byte[2]     month     1–12
byte[3]     day       1–31
byte[4]     hour      0–23
byte[5]     minute    0–59
byte[6]     second    0–59
byte[7]     day_of_week  0=Mon … 6=Sun
byte[8]     fractions256
byte[9]     adjust_reason
byte[10]    unknown
```

---

## 6. Real-time Sensor Stream (0x0002)

Characteristic: `00000002-0000-3512-2118-0009af100700`

Broadcasts paired notifications approximately once per second.
**Does not require authentication.**

### 6-byte packet — Calorie counter
```
byte[0]     0x10  (type marker)
byte[1]     sequence counter (1–255, wraps)
byte[2]     0xFF  (constant)
byte[3]     0x7F  (constant)
bytes[4:6]  calories  uint16 LE  (slowly incrementing)
```

### 11-byte packet — Activity counter
```
byte[0]     0x07  (type marker)
byte[1]     sequence counter (1–255, wraps)
byte[2]     0x10  (constant)
bytes[3:7]  internal timestamp  uint32 LE  (ms, device epoch, +1000/sec)
bytes[7:9]  steps  uint16 LE  ← STALE (device cache, does NOT update in real-time)
bytes[9:11] unknown
```

**WARNING**: The step count at bytes[7:9] is a **stale device cache value**. It does not update when the user walks. Real step data must be obtained from the historical activity fetch (type 0x01, see §7). Only the calorie counter from 6-byte packets is reliably real-time.

---

## 7. Historical Data Fetch (0x0004 / 0x0005)

Control char: `00000004-0000-3512-2118-0009af100700` (write-without-response + notify)
Data char:    `00000005-0000-3512-2118-0009af100700` (notify)

### Fetch command format (10 bytes, write to 0x0004)
```
byte[0]    CMD_INIT = 0x01
byte[1]    type code  (see table below)
bytes[2:4] year  uint16 LE
byte[4]    month
byte[5]    day
byte[6]    hour
byte[7]    minute
byte[8]    timezone_hour  (0x00)
byte[9]    timezone_min   (0x00)
```
**Note: 8-byte format (without timezone bytes) gets no response. Must use 10 bytes.**

### Control response (read from 0x0004 notifications)

**Status 0x01 — data available (16 bytes)**
```
byte[0]    0x10
byte[1]    0x01
byte[2]    0x01  (data available)
bytes[3:7] expected_count  uint32 LE  (number of records, NOT bytes)
bytes[7:9] year of oldest available record  uint16 LE
byte[9]    month
byte[10]   day
byte[11]   hour
byte[12]   minute
bytes[13+] padding
```

**Status 0x0b — locked (requires ECDH auth)**
```
10 01 0b
```

**Status 0x05 — no data available**
```
10 01 05
```

### Transfer protocol
```
1. Write [0x01, type, year_lo, year_hi, month, day, hour, min, 0x00, 0x00]  to 0x0004
2. Wait for control notification → check byte[2]
   - 0x01 = data available → continue
   - 0x0b = locked (ECDH auth needed)
   - 0x05 = no data
3. Write [0x02, 0x01] + checksum_bytes  to 0x0004  (ACK + start transfer)
4. Receive 241-byte chunks on 0x0005 until stall (5s no data)
5. Write [0x02, 0x01, 0x32, 0x00, 0x00, 0x00, 0x00]  to 0x0004  (completion ACK)
```

### Chunk format (241 bytes on 0x0005)
```
byte[0]    chunk sequence number (0, 1, 2 … wraps at 255)
bytes[1:]  240 bytes of payload data
```
Strip the first byte from each chunk to get clean data.

### Type codes

| Code | Auth Required | Description | Record Size | Status |
|------|---------------|-------------|-------------|--------|
| **0x01** | ECDH | Activity (per-minute samples) | 8 bytes | ✅ Working |
| **0x13** | ECDH | Stress (auto, per-minute) | 1 byte | ✅ Working (often empty) |
| **0x25** | ECDH | SpO2 readings | 65 bytes | ✅ Working |
| **0x48** | ECDH | Sleep session data | variable (594B blobs) | ✅ Working |
| **0x49** | ECDH | HRV readings | 1 byte | ✅ Working |
| **0x55** | None | HR per-second history | 5 bytes | ✅ Working |
| 0x12 | ECDH | Stress (manual) | 5 bytes | Untested |
| 0x26 | ECDH | SpO2 (sleep) | variable | Untested |
| 0x56 | None | Unknown (one-time queue) | unknown | Data consumed on first fetch |
| 0x05, 0x07, 0x2e, 0x3a | — | Various | — | Status 0x0b or 0x05 |

---

## 8. Type 0x55 — Per-second Heart Rate History

### Raw data format
- **Chunk size**: 241 bytes
- **Payload**: strip first byte (chunk seq) → 240 bytes data
- **Record size**: 5 bytes
- **Records per chunk**: 48

### 5-byte record structure
```
bytes[0:2]  counter16    uint16 LE  (low 16 bits of seconds counter)
byte[2]     counter_high uint8      (high byte of seconds counter, base 0xC8)
byte[3]     0x69         constant marker
byte[4]     bpm          uint8      (heart rate in BPM)
```

### Timestamp reconstruction
```python
full_counter = (byte2 - 0xC8) * 65536 + counter16
offset_sec   = full_counter - first_record_counter
timestamp    = fetch_start_time + timedelta(seconds=offset_sec)
```

---

## 9. Type 0x01 — Per-minute Activity Data

**Requires ECDH authentication (Phase 2).**

### 8-byte record structure (per minute)
```
byte[0]     kind        Activity category (0x50=sedentary, 0x60=light, 0x78=resting/sleep)
byte[1]     intensity   Movement intensity (0–255)
byte[2]     steps       Steps taken in this minute (0–255)
byte[3]     heart_rate  HR BPM (0 if no reading)
bytes[4:8]  extra       Additional flags (SpO2/stress markers, values 0x05/0xFF/0x80 observed)
```

### Step count extraction
```python
payload = b''.join(chunk[1:] for chunk in data_chunks)  # strip seq bytes
total_steps = sum(payload[i*8 + 2] for i in range(len(payload) // 8))
```

### Daily aggregation
The `expected_count` field from the control response is the **number of minutes** of data. Sum byte[2] (steps) per day using `start_timestamp + timedelta(minutes=i)` for each record.

### Observed values
- `kind=0x78` dominates during sleep/rest periods (steps=0, low HR)
- `kind=0x50` during sedentary activity
- `intensity` correlates with movement level
- `extra` bytes: byte[4] typically 0x05, byte[5] typically 0xFF (no reading), bytes[6:7] typically 0x80 0x80

---

## 10. Type 0x25 — SpO2 Data

**Requires ECDH authentication.**

65-byte records with version byte, status flags, and SpO2 percentage value. Decoding follows Gadgetbridge `HuamiSpO2Parser` format.

---

## 11. Type 0x13 — Stress Data (Auto)

**Requires ECDH authentication.**

1 byte per minute: stress level 0–100 (0xFF = no reading for that minute). Often returns only 1-2 bytes of data, suggesting the Helio Strap does not actively compute stress. The Zepp app may handle stress computation from raw HR data.

---

## 12. Type 0x49 — HRV Data

**Requires ECDH authentication.**

Per-minute HRV readings. Each record contains RMSSD and SDNN values. Thousands of data points returned (7000+ observed for ~5 days of data).

---

## 13. Type 0x48 — Sleep Session Data

**Requires ECDH authentication.**

594-byte session blobs containing sleep stage arrays (deep, light, REM, awake) with timestamps.

---

## 14. Device Configuration (endpoint 0x000A via 0x0016/0x0017)

**Requires ECDH authentication.**

The Zepp OS Config Service allows reading/writing device settings via the chunked protocol.

### Config Command Format

#### CMD_SET (0x05) — write a config value
```
Payload on endpoint 0x000A:
byte[0]     0x05  (CMD_SET)
byte[1]     config_group
byte[2]     config_version
byte[3]     config_id
byte[4]     config_type  (0x01=BOOL, 0x06=SHORT, 0x10=STRING)
bytes[5+]   value
```

#### CMD_GET (0x04) — read a config value
```
Payload on endpoint 0x000A:
byte[0]     0x04  (CMD_GET)
byte[1]     config_group
byte[2]     config_version
byte[3]     config_id
```

Response (CMD_RESPONSE = 0x06):
```
byte[0]     0x06
byte[1]     config_group
byte[2]     config_version
byte[3]     config_id
byte[4]     config_type
bytes[5+]   value
```

### Health Config Group (0x08, version 0x03)

| Config ID | Type | Name | Description |
|-----------|------|------|-------------|
| `0x5D` | BOOL | `HR_AUTO_MEASURE` | Continuous heart rate monitoring |
| `0x5E` | BOOL | `BLOOD_OXYGEN_AUTO` | Auto blood oxygen measurement |
| `0x5F` | BOOL | `SPO2_AUTO_MEASURE` | Auto SpO2 during sleep |
| `0x60` | BOOL | `TEMP_AUTO_MEASURE` | Auto temperature measurement |

### Example: Enable auto SpO2
```python
payload = bytes([0x05, 0x08, 0x03, 0x5F, 0x01, 0x01])  # CMD_SET, HEALTH, v3, SPO2_AUTO, BOOL, True
frame = build_chunked_frame(endpoint=0x000A, payload=payload)
await client.write_gatt_char("0x0016", frame)
```

---

## 15. Sensor Control (0x0006) — HR Keepalive

Characteristic: `00000006-0000-3512-2118-0009af100700`
Permissions: **write-without-response, notify** (read returns "not permitted")

### Working command: HR enable
```
WRITE: [0x15, 0x01, 0x01]
```
Used as part of the HR keepalive cycle (see §3). Must be combined with re-subscribing to 0x2A37.

### Non-functional commands (tested)

| Command | Result |
|---------|--------|
| `01 00`, `01 25`, `01 12`, `01 49` | No response |
| `15 02 01`, `15 03 01` | Connection dropped |
| `01 00 25 00`, `01 00 12 00` | Connection dropped |

On-demand SpO2/stress/HRV measurements cannot be triggered via 0x0006. Use device config (§14) to enable auto-measurement instead.

---

## 16. Summary — What Works via Direct BLE

| Feature | Method | Auth Required | Status |
|---------|--------|---------------|--------|
| Real-time HR | 0x2A37 notify + keepalive | None | ✅ Working (1/sec) |
| Historical HR | Fetch type 0x55 | None | ✅ Working (per-second, accumulates) |
| Battery level | 0x2A19 read | None | ✅ Working |
| Calories (real-time) | 0x0002 sensor stream | None | ✅ Working |
| Time sync | 0x2A2B write | None | ✅ Working |
| Activity (steps per day) | Fetch type 0x01 | **ECDH** | ✅ Working (per-minute 8-byte samples) |
| SpO2 history | Fetch type 0x25 | **ECDH** | ✅ Working |
| Sleep sessions | Fetch type 0x48 | **ECDH** | ✅ Working |
| Stress (auto) | Fetch type 0x13 | **ECDH** | ✅ Working (often empty) |
| HRV history | Fetch type 0x49 | **ECDH** | ✅ Working |
| Device config | Endpoint 0x000A | **ECDH** | ✅ Working (SpO2 auto enable confirmed) |
| Steps (real-time) | 0x0002 sensor stream | None | ⚠️ Stale cache (unreliable) |
| On-demand SpO2 trigger | — | — | ❌ Not discovered |

---

## 17. Auth Key Extraction

The 16-byte auth key is required for both Phase 1 and Phase 2 authentication. It is unique per device-account pairing and changes on factory reset.

### Automated extraction
```bash
./extract_auth_key.sh
```
Requires: Android phone with ADB + modified Zepp app.
Queries `api.amazfit.com/users/{id}/devices` for the `auth_key` in `additionalInfo`.

### Manual methods
1. **Modified Zepp APK**: Intercept `apptoken` via logcat, then query the devices API
2. **Gadgetbridge**: Pair device → Export Keys → find `DEVICE_KEY` in JSON

---

## 18. Test Scripts

All test scripts are in the `tests/` directory and use `.env` for credentials.

| Script | Purpose |
|--------|---------|
| `tests/test_zepp_auth.py` | Full ECDH auth handshake + data fetch validation |
| `tests/test_decode_activity.py` | Activity type 0x01 raw data analysis + record format discovery |
| `tests/test_hr_poll.py` | HR keepalive methods (re-subscribe vs sensor ctrl) |
| `tests/test_hr_realtime.py` | Real-time HR streaming tests |
| `tests/test_find_steps.py` | Step count protocol investigation |
| `tests/test_read_steps.py` | GATT service enumeration for step-related chars |
| `tests/test_spo2_config.py` | Device config: SpO2 auto-enable via endpoint 0x000A |
| `extract_auth_key.sh` | Automated auth key extraction via ADB + Zepp API |
