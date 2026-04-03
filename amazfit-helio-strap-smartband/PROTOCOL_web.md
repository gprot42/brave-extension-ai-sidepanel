# Amazfit Helio Strap — Huami / Zepp Cloud API Reference

All findings are based on reverse engineering of the Zepp app traffic and
community research. Tested against the EU region (`eu-central-1`).

---

## 1. Overview

The Zepp app syncs data from the band to Huami's cloud. Two API surfaces exist:

| API | Auth method | Status |
|-----|-------------|--------|
| **Internal app API** (`api-mifit-*.huami.com`) | `apptoken` (2-step login) | Working |
| **Public OAuth API** (`api-open.huami.com`) | OAuth 2.0 Bearer token | Developer portal broken — limited access |
| **Device API** (`api.amazfit.com`) | `apptoken` | Working (auth key extraction) |

The internal app API is what the Zepp app itself uses. The OAuth API developer
portal at `dev.huami.com` is defunct. The Device API is used for auth key extraction.

**Note:** Since we now have full BLE access to all health data via ECDH authentication
(see `PROTOCOL_bluetooth.md`), the cloud API is primarily useful for:
- Auth key extraction (`api.amazfit.com/users/{id}/devices`)
- Backup/cross-reference of data
- Historical data from before BLE access was established

---

## 2. Regional Base URLs

| Region | Data host | Events host |
|--------|-----------|-------------|
| `eu-central-1` (default) | `https://api-mifit-de2.huami.com` | `https://api-mifit-de2.zepp.com` |
| `us-west-2` | `https://api-mifit.huami.com` | `https://api-mifit.zepp.com` |
| `cn` | `https://api-mifit.huami.com` | `https://api-mifit.zepp.com` |

Auth hosts (all regions):
- User/token endpoint: `https://api-user.huami.com`
- Login/apptoken exchange: `https://account.huami.com`
- Zepp v2 fallback: `https://api-user-us2.zepp.com`
- Device management: `https://api.amazfit.com`

---

## 3. Authentication — Internal App API (apptoken)

### Step 1 — Get access token

```http
POST https://api-user.huami.com/registrations/{email}/tokens
Content-Type: application/x-www-form-urlencoded

state=REDIRECTION
client_id=HuaMi
redirect_uri=https://s3-us-west-2.amazonaws.com/hm-registration/successsignin.html
token=access
password={password}
```

Response: HTTP 302/303 redirect.
Extract `access` param from the `Location` header URL query string.

**Fallback (newer Zepp accounts):**
```http
POST https://api-user-us2.zepp.com/v2/registrations/tokens
Content-Type: application/x-www-form-urlencoded

emailOrPhone={email}
password={password}
state=REDIRECTION
client_id=HuaMi
redirect_uri=https://s3-us-west-2.amazonaws.com/hm-registration/successsignin.html
region=eu-central-1
token=access
country_code=GB
```

### Step 2 — Exchange for apptoken

```http
POST https://account.huami.com/v2/client/login
Content-Type: application/x-www-form-urlencoded

app_name=com.xiaomi.hm.health
dn=account.huami.com,api-user.huami.com,api-mifit.huami.com,api-mifit-de2.huami.com,api-mifit-de2.zepp.com,api-mifit.zepp.com
device_id=02:00:00:00:00:00
device_model=android_phone
app_version=4.0.9
allow_registration=false
third_name=huami
grant_type=access_token
country_code=GB
code={access_token_from_step1}
```

Response JSON:
```json
{
  "token_info": {
    "app_token": "...",
    "user_id": "...",
    "login_token": "..."
  }
}
```

- `app_token` → use as `apptoken` header on all data requests
- `user_id` → used in data endpoint URL paths
- Token lifetime: months (persists until revoked by re-login)

### Authentication header

All data requests use a raw HTTP header — **not** Bearer auth:

```
apptoken: {app_token}
```

---

## 4. Auth Key Extraction API

**This is the primary use of the cloud API** — extracting the BLE auth key for ECDH authentication.

### Endpoint

```http
GET https://api.amazfit.com/users/{user_id}/devices
apptoken: {app_token}
appname: com.huami.midong
```

### Response

```json
{
  "items": [
    {
      "deviceType": "...",
      "deviceSource": "...",
      "additionalInfo": "{\"auth_key\": \"b80228f1d2863ddf521c3c3fd2de8ad4\"}"
    }
  ]
}
```

The `additionalInfo` field is a JSON-encoded string. Parse it to extract `auth_key` (32 hex chars = 16 bytes).

### Automated extraction

```bash
./extract_auth_key.sh
```

This script:
1. Captures `apptoken` from modified Zepp app via `adb logcat`
2. Extracts user ID from logs or API
3. Calls the devices endpoint above
4. Parses `auth_key` from `additionalInfo`
5. Saves to `.env` and optionally pushes to running backend

---

## 5. Data Endpoints

### 5.1 band_data.json — Sleep & Activity

```http
GET {data_host}/v1/data/band_data.json
apptoken: {token}

?query_type=summary
&device_type=android_phone
&userid={userid}
&from_date=YYYY-MM-DD
&to_date=YYYY-MM-DD
```

`query_type=detail` adds a `data_hr` binary blob (HR history, see §5.2).

**Response structure:**
```json
{
  "data": [
    {
      "date_time": "YYYY-MM-DD",
      "summary": "<base64-encoded JSON>"
    }
  ]
}
```

The `summary` field is a base64-encoded JSON string. After decoding:

```json
{
  "slp": {
    "dp": 42,
    "lt": 180,
    "rem": 60,
    "wk": 12,
    "stage": [
      { "mode": 4, "start": 1234567890, "end": 1234568000 }
    ]
  },
  "stp": {
    "ttl": 8200,
    "dis": 6500,
    "cal": 320
  }
}
```

Sleep stage `mode` values:

| Value | Stage |
|-------|-------|
| 4 | Light sleep |
| 5 | Deep sleep |
| 7 | Awake |
| 8 | REM |

### 5.2 HR History (detail query)

```http
GET {data_host}/v1/data/band_data.json?query_type=detail&userid={userid}&from_date=YYYY-MM-DD&to_date=YYYY-MM-DD
```

Response includes a `data_hr` field: binary blob of 2-byte big-endian unsigned shorts, one per minute. Values above 200 = no reading.

### 5.3 Events — SpO2 & Stress

```http
GET {events_host}/users/{userid}/events
apptoken: {token}

?from={unix_ms}
&to={unix_ms}
&eventType={type}
&limit=1000
&timeZone=Europe/London
```

| eventType | Data |
|-----------|------|
| `blood_oxygen` | SpO2 readings (`extra.spo2`) |
| `stress` | Stress level (`extra.stress_level` or `extra.score`) |

---

## 6. Public OAuth 2.0 API

**Base URL:** `https://api-open.huami.com`
**Status:** Developer portal defunct — cannot register new apps

| Scope | Data |
|-------|------|
| `sleep` | Sleep logs |
| `heartrate` | HR with timestamps |
| `activity` | Steps, distance, calories |
| `profile` | User profile |

---

## 7. Data Availability — BLE vs Cloud

| Metric | BLE (ECDH) | Internal App API | Notes |
|--------|------------|------------------|-------|
| HR (per-second) | ✅ Type 0x55 | ✅ Per-minute only | BLE has higher resolution |
| HR (real-time) | ✅ 0x2A37 notify | — | BLE only |
| Steps / activity | ✅ Type 0x01 | ✅ `band_data.json` | BLE per-minute, cloud daily total |
| Sleep stages | ✅ Type 0x48 | ✅ `band_data.json` | Both work |
| SpO2 | ✅ Type 0x25 | ✅ `/events` | Both work |
| Stress | ✅ Type 0x13 | ✅ `/events` | BLE often empty (device may not compute) |
| HRV | ✅ Type 0x49 | ❌ Not found | BLE only |
| Battery | ✅ 0x2A19 | — | BLE only |
| Device config | ✅ Endpoint 0x000A | — | BLE only |

**Recommendation**: Use BLE (ECDH) as primary data source — it provides higher resolution data and doesn't require cloud authentication. The cloud API serves as a fallback and is essential for auth key extraction.

---

## 8. Integration Notes

- Credentials (email, password, apptoken, userid) are stored in `.env` only.
- After first login the `apptoken` + `userid` are persisted to `.env`.
- The `apptoken` auth header must be lowercase (`apptoken`, not `Apptoken`).
- `follow_redirects=False` is required on the Step 1 POST.
- Fallback: if the primary data host fails, retry with `api-mifit.zepp.com`.

---

## 9. Rate Limiting

Huami's login endpoint enforces a **per-account rate limit**:

- **HTTP 429** after ~10–20 login attempts in a short period
- **Lockout duration**: ~6–24 hours (per-account, not per-IP)
- The `apptoken` itself is **not** rate-limited — data endpoints can be called freely
- Rate limiting is per email address, not per IP

### Mitigation

Since BLE now provides all health data, the cloud API is rarely needed:
- Auth key extraction: one-time operation per factory reset
- Historical data: only needed for data predating BLE connection
- If rate-limited, wait and use the cached `apptoken` from `.env`
