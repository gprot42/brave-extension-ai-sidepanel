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

## 10. Type 0x25 — SpO2 Data (Normal)

**Requires ECDH authentication.**

Decoding follows Gadgetbridge `FetchSpo2NormalOperation.java`.

### Raw data format
- **Version header**: 1 byte (expected `0x02`)
- **Record size**: 65 bytes
- **Validation**: `(stripped_length - 1) % 65 == 0`

### 65-byte record structure
```
bytes[0:4]  timestamp     int32 LE  (Unix epoch seconds)
byte[4]     spo2_raw      int8      (signed — see decoding below)
bytes[5:65] unknown       60 bytes  (mostly zeros, additional metadata)
```

### SpO2 value decoding (sign-bit encoding)
```
If bit 7 is set (raw >= 0x80):
  → Auto measurement (device-initiated, e.g., during sleep)
  → actual_spo2 = raw_byte - 128

If bit 7 is clear (raw < 0x80):
  → Manual measurement (user-initiated from device)
  → actual_spo2 = raw_byte
```

Examples:
- Raw `0xE1` (225) → auto, SpO2 = 225 - 128 = **97%**
- Raw `0x60` (96) → manual, SpO2 = **96%**

### Verified data sizes
| Stripped bytes | - 1 header | ÷ 65 | Records |
|----------------|------------|------|---------|
| 3641 | 3640 | 56.0 | 56 |
| 4031 | 4030 | 62.0 | 62 |
| 4096 | 4095 | 63.0 | 63 |

### Type 0x26 — SpO2 Sleep (untested)
30-byte records with version header. Each record: 4-byte timestamp, 1-byte SpO2 (no sign-bit encoding), 1-byte duration, 6-byte high values, 6-byte low values, 8-byte signal quality, 4-byte extended.

### Auto-enable

SpO2 and health monitoring must be enabled on the device via config endpoint `0x000A`.
All config commands **require ECDH authentication** and **AES encryption** (see §14).

**SET command wire format (Gadgetbridge ZeppOsConfigService):**
```
[0x05]      CMD_SET
[0x08]      Config group: HEALTH
[0x03]      Config version
[0x00]      Padding / reserved
[0x01]      Arg count (1 config at a time)
[id]        Config ID (see table below)
[0x0b]      Type: BOOL (Gadgetbridge ConfigType.BOOL = 0x0b)
[0x01]      Value: 0x01=enabled, 0x00=disabled
```

**GET (request) command:**
```
[0x03]      CMD_REQUEST
[0x01]      Include constraints flag
[0x08]      Config group: HEALTH
[0x01]      Arg count
[id]        Config ID
```

**Health config IDs (empirically confirmed via encrypted GET readback):**
| ID | Name | Type | Status | Notes |
|----|------|------|--------|-------|
| `0x04` | SPO2_ALL_DAY_MONITORING | BOOL | **Confirmed** | SET + GET readback returns value=True |
| `0x12` | SLEEP_BREATHING_QUALITY | BOOL | Used | Enables sleep-phase SpO2 collection |
| `0x17` | HR_ALL_DAY_MONITORING | BOOL | Used | Enables continuous heart rate monitoring |
| `0x18` | HR_HIGH_ALERT | BYTE | Untested | Heart rate high threshold |
| `0x19` | HR_LOW_ALERT | BYTE | Untested | Heart rate low threshold |
| `0x31` | Unknown (was SPO2 guess) | BOOL | **Wrong** | SET ACK'd but GET returns value=False (doesn't stick) |
| `0x32` | SPO2_LOW_ALERT | BYTE | Untested | SpO2 low threshold alert |
| `0x39` | STRESS_ALL_DAY_MONITORING | BOOL | Used | Enables periodic stress measurement |
| `0x5a` | — | — | **Invalid** | SET returns error status 0x05 (not found) |

**Previously incorrect IDs (do NOT use):**
- ~~0x31 for SpO2~~ — SET ACK's but GET confirms value is not stored. Use `0x04` instead.
- ~~0x5a~~ — Returns error status 0x05 (config ID not found on device).
- ~~0x5D, 0x5E, 0x5F, 0x60~~ — These were guessed and do not exist on the Helio Strap.
- ~~CONFIG_TYPE_BOOL = 0x00~~ — Wrong. Gadgetbridge uses `0x0b` for BOOL. Using 0x00 results in SET ACK `0602` (wrong type) instead of `0601` (success).

The app enables SpO2 all-day (`0x04`), sleep breathing (`0x12`), and stress all-day (`0x39`) on connect after successful ECDH auth, using AES-encrypted config frames.

**Note on on-demand SpO2:** Gadgetbridge has not implemented on-demand (phone-triggered) SpO2 measurement for Zepp OS. Only the device itself can initiate a manual reading. The endpoint and commands are unknown without BLE sniffing.

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

Each sleep session is a fixed **594-byte blob**. Multi-night fetches return N×594 bytes concatenated.

### Session blob structure (594 bytes)

Confirmed by Gadgetbridge `HuamiSleepSessionSampleProvider` and `libdataProcess.so` string analysis.

```
Offset  Size  Field                 Notes
──────  ────  ────────────────────  ──────────────────────────────
0x00    4     ts_session            uint32 LE, Unix epoch — session reference timestamp
0x04    4     ts_midnight           uint32 LE, Unix epoch — midnight of the sleep date
0x08    1     unknown               always 0x01
0x09    1     unknown               always 0x01
0x0A    2     sleep_start_min       uint16 LE — minutes from midnight (onset)
0x0C    2     sleep_end_min         uint16 LE — minutes from midnight (wakeup)
0x15    1     avg_hr                uint8 — average heart rate during session
0x16    1     score                 uint8 — sleep quality score (0–100)
0x54    1     num_stages            uint8 — count of stage entries that follow
0x56    5×N   stage_entries[]       see Stage Entry format below
        ...   (zero padding)        fills remainder of blob up to offset 0x24A
0x24A   2     total_rem_min         uint16 LE — REM sleep minutes (device pre-computed)
0x24C   2     total_light_min       uint16 LE — light sleep minutes
0x24E   2     total_deep_min        uint16 LE — deep sleep minutes
0x250   2     total_wake_min        uint16 LE — awake minutes within session
```

### Stage entry format (5 bytes each, starting at offset 0x56)

```
bytes[0:2]  seg_start    uint16 LE — start minute (relative to ts_midnight)
bytes[2:4]  seg_end      uint16 LE — end minute (relative to ts_midnight)
byte[4]     seg_type     uint8     — stage type code
```

### Stage type codes

| Type | Stage   | Color in Zepp App |
|------|---------|-------------------|
| `4`  | Light   | `sleep_light_color` |
| `5`  | Deep    | `sleep_deep_color` |
| `7`  | Awake   | `sleep_wake_color` |
| `8`  | REM     | `sleep_rem_color` |

### Night date attribution

The `ts_session` timestamp is converted to local time. If the local hour is before noon (12:00), the session is attributed to the **previous** calendar day (e.g., 3am April 5 local → night of April 4).

### Pre-computed totals

The device firmware pre-computes sleep stage totals at offsets 0x24A–0x251. These values match (or closely approximate) the sum of stage entry durations. The app prefers blob totals when non-zero, falling back to summing stage entries.

### Native algorithm (`libdataProcess.so`)

The Zepp app uses a native C library for sleep analysis that takes **3 bytes per minute** of activity data + **1 byte per minute** HR data + PersonInfo (gender, height, weight, age). The Helio Strap firmware runs this algorithm on-device and stores the results as 594-byte session blobs. Our app reads the pre-computed results directly — no client-side sleep classification needed.

Key native functions (from library strings):
- `findStartSleepAndWakeUp()` — boundary detection using HR + activity
- `coreAlgoForGetSleepTime()` — core sleep time computation
- `getStageSleep()` — stage classification
- `find_awake()` — awake period detection
- `findNoWearSection()` — not-worn period elimination

---

## 14. Device Configuration (endpoint 0x000A via 0x0016/0x0017)

**Requires ECDH authentication + AES encryption.**

The Zepp OS Config Service allows reading/writing device settings via the chunked protocol.
Config commands sent without encryption are **silently dropped** (no response, timeout).

### Encryption Requirement (Discovered via Testing)

| Test | Result |
|------|--------|
| Unencrypted config before ECDH | TIMEOUT (all IDs) |
| Unencrypted config after ECDH | TIMEOUT (all IDs) |
| **Encrypted config after ECDH** | **Response received** |

**Conclusion**: All config commands on endpoint 0x000A **must** be AES-encrypted using the ECDH session key.

### AES Encryption Format (Gadgetbridge Huami2021ChunkedEncoder)

Post-ECDH, all chunked frames must be encrypted:

1. **Message key derivation** (per-frame):
   ```python
   message_key[i] = session_key[i] ^ handle  # i = 0..15
   ```
   Where `handle` is the per-frame counter byte from the chunked header (byte[3]).

2. **Plaintext construction**:
   ```
   [original_payload]           (N bytes — the actual config command)
   [enc_write_seq_nr]           (4 bytes, uint32 LE — increments per encrypted write)
   [CRC32(payload + seq_nr)]    (4 bytes, uint32 LE)
   [zero_padding]               (pad to 16-byte boundary)
   ```

3. **Encrypt**: AES-ECB with `message_key` (each 16-byte block independently)

4. **Frame header flag**: `0x0b` = `FLAG_FIRST(0x01) | FLAG_LAST(0x02) | FLAG_ENCRYPTED(0x08)`
   - Header bytes[5:7] contain the **original** (unencrypted) payload length
   - Header bytes[11+] contain the **encrypted** payload (longer due to seq+crc+padding)

5. **Decryption** of responses: Same process — derive `message_key` from response handle byte, decrypt, extract first `orig_len` bytes.

### Encrypted Chunked Frame Format

```
byte[0]     0x03  (protocol marker)
byte[1]     0x0b  (flags: first + last + encrypted)
byte[2]     0x00  (reserved)
byte[3]     handle  (counter, wraps at 0xFF — used for message key derivation)
byte[4]     0x00  (chunk count: 0 = single chunk)
bytes[5:7]  original_payload_length  uint16 LE  (length BEFORE encryption)
bytes[7:9]  0x00 0x00  (padding)
bytes[9:11] endpoint_id  uint16 LE  (0x000A for config)
bytes[11+]  encrypted_payload  (AES-ECB encrypted, padded to 16-byte boundary)
```

### Config Command Format

#### CMD_SET (0x05) — write a config value
```
Payload on endpoint 0x000A (before encryption):
byte[0]     0x05  (CMD_SET)
byte[1]     config_group      (0x08 = HEALTH)
byte[2]     config_version    (0x03)
byte[3]     0x00  (padding / reserved)
byte[4]     arg_count         (0x01 = one config item)
byte[5]     config_id         (e.g., 0x04 for SpO2)
byte[6]     config_type       (0x0b = BOOL)
byte[7]     value             (0x01 = enabled, 0x00 = disabled)
```

#### CMD_REQUEST (0x03) — read a config value
```
Payload on endpoint 0x000A (before encryption):
byte[0]     0x03  (CMD_REQUEST)
byte[1]     0x01  (include constraints)
byte[2]     config_group      (0x08 = HEALTH)
byte[3]     arg_count         (0x01)
byte[4]     config_id
```

### Response Format

**SET response** (CMD_RESPONSE = 0x06):
```
byte[0]     0x06  (CMD_RESPONSE)
byte[1]     status
```

| Status | Meaning |
|--------|---------|
| `0x01` | Success — config value written |
| `0x02` | Wrong type — config_type byte incorrect |
| `0x05` | Error — config ID not found on device |

**GET response** (CMD_GET = 0x04):
```
byte[0]     0x04
byte[1]     0x01
byte[2]     config_group   (0x08)
byte[3]     config_version (0x03)
byte[4]     0x01
byte[5]     0x01
byte[6]     config_id
byte[7]     config_type    (0x0b)
byte[8]     0x01
byte[9]     0x00
byte[10]    value          (0x00 or 0x01)
```

### Config Types (Gadgetbridge ZeppOsConfigService.ConfigType)

| Value | Type | Size |
|-------|------|------|
| `0x0b` | BOOL | 1 byte (0x00 or 0x01) |
| `0x01` | BYTE | 1 byte |
| `0x06` | SHORT | 2 bytes LE |
| `0x10` | STRING | Null-terminated |

**Critical**: Using the wrong type byte (e.g., `0x00` instead of `0x0b` for BOOL) results in SET response `0x02` (wrong type) — the device acknowledges the command but does not apply it.

### Health Config Group (0x08, version 0x03) — Confirmed IDs

| Config ID | Type | Name | Status | Diagnostic Result |
|-----------|------|------|--------|-------------------|
| **`0x04`** | BOOL | SPO2_ALL_DAY_MONITORING | **Confirmed** | SET→`0601`, GET→value=True |
| `0x12` | BOOL | SLEEP_BREATHING_QUALITY | Used | SET→`0601` |
| `0x17` | BOOL | HR_ALL_DAY_MONITORING | Used | SET→`0601` |
| `0x39` | BOOL | STRESS_ALL_DAY_MONITORING | Used | SET→`0601` |
| `0x31` | BOOL | Unknown | **Wrong for SpO2** | SET→`0601` but GET→value=False |
| `0x5a` | — | — | **Invalid** | SET→`0605` (not found) |

### Example: Enable auto SpO2 (encrypted)
```python
from Crypto.Cipher import AES
import struct, zlib

# Build config payload
payload = bytes([0x05, 0x08, 0x03, 0x00, 0x01, 0x04, 0x0b, 0x01])

# Append seq_nr + CRC32 + padding
seq = struct.pack('<I', enc_write_seq_nr)
to_crc = payload + seq
crc = struct.pack('<I', zlib.crc32(to_crc) & 0xFFFFFFFF)
plaintext = to_crc + crc + b'\x00' * ((16 - len(to_crc + crc) % 16) % 16)

# Encrypt
handle = next_handle()
msg_key = bytes([session_key[i] ^ handle for i in range(16)])
encrypted = AES.new(msg_key, AES.MODE_ECB).encrypt(plaintext)

# Build frame
frame = bytes([0x03, 0x0b, 0x00, handle, 0x00,
               len(payload) & 0xFF, 0x00, 0x00, 0x00, 0x0A, 0x00]) + encrypted
await client.write_gatt_char("0x0016", frame)
enc_write_seq_nr += 1
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
| `tests/test_spo2_decode.py` | SpO2 raw data hex dump + record format analysis |
| `extract_auth_key.sh` | Automated auth key extraction via ADB + Zepp API |
