#!/usr/bin/env python3
"""
Decode raw_fetch_0x55.bin from the Helio Strap.

Known facts:
- 1,381,809 bytes total, 5734 chunks of 241 bytes each
- Each chunk starts with a 1-byte sequence number (0x00, 0x01, ...)
- Remaining 240 bytes per chunk = data payload
- Fetch header said: data starts from 2026-03-28 17:33
- Records appear to be 5 bytes each: [seq_lo, seq_hi, b1, b2, value]
- b1=0xc8, b2=0x69 seem constant in early records, value looks like HR (76-90)
"""

import struct
from datetime import datetime, timedelta

FILENAME = "raw_fetch_0x55.bin"
START_TIME = datetime(2026, 3, 28, 17, 33, 0)  # from fetch response header

with open(FILENAME, "rb") as f:
    raw = f.read()

print(f"File size: {len(raw)} bytes")

# Step 1: Strip chunk sequence bytes (first byte of each 241-byte chunk)
chunks = []
pos = 0
while pos < len(raw):
    chunk_size = min(241, len(raw) - pos)
    seq_byte = raw[pos]
    payload = raw[pos + 1:pos + chunk_size]
    chunks.append((seq_byte, payload))
    pos += chunk_size

print(f"Chunks: {len(chunks)}")
data = b"".join(p for _, p in chunks)
print(f"Payload size: {len(data)} bytes")
print(f"Records (5-byte): {len(data) // 5}")
print(f"Remainder: {len(data) % 5} bytes")

# Step 2: Parse 5-byte records
records = []
for i in range(0, len(data) - 4, 5):
    rec = data[i:i+5]
    seq = struct.unpack_from("<H", rec, 0)[0]  # little-endian 16-bit sequence
    b1 = rec[2]
    b2 = rec[3]
    val = rec[4]
    records.append((seq, b1, b2, val))

print(f"\nTotal records parsed: {len(records)}")

# Step 3: Analyze sequence numbers
seqs = [r[0] for r in records]
print(f"\nSequence range: {min(seqs)} - {max(seqs)}")
print(f"First 20 sequences: {seqs[:20]}")
print(f"Sequence diffs (first 20): {[seqs[i+1]-seqs[i] for i in range(min(19, len(seqs)-1))]}")

# Step 4: Analyze b1, b2 fields
b1_vals = set(r[1] for r in records)
b2_vals = set(r[2] for r in records)
print(f"\nUnique b1 values: {len(b1_vals)} — range [{min(b1_vals)}, {max(b1_vals)}]")
print(f"Unique b2 values: {len(b2_vals)} — range [{min(b2_vals)}, {max(b2_vals)}]")
if len(b1_vals) <= 20:
    print(f"  b1 values: {sorted(b1_vals)}")
if len(b2_vals) <= 20:
    print(f"  b2 values: {sorted(b2_vals)}")

# Step 5: Analyze val field
vals = [r[3] for r in records]
print(f"\nValue range: [{min(vals)}, {max(vals)}]")
print(f"Value mean: {sum(vals)/len(vals):.1f}")

# Check if val looks like HR (40-200 BPM typical)
hr_range = [v for v in vals if 40 <= v <= 200]
print(f"Values in HR range (40-200): {len(hr_range)} / {len(vals)} ({100*len(hr_range)/len(vals):.1f}%)")

# Step 6: Print first 30 decoded records with timestamps
print(f"\n{'='*70}")
print(f"First 30 records (assuming 1-second intervals from {START_TIME}):")
print(f"{'='*70}")
print(f"{'#':>6} {'Seq':>6} {'b1':>4} {'b2':>4} {'Val':>4}  Timestamp")
print(f"{'-'*6} {'-'*6} {'-'*4} {'-'*4} {'-'*4}  {'-'*20}")

# Use first sequence as base
base_seq = records[0][0]
for i, (seq, b1, b2, val) in enumerate(records[:30]):
    offset_sec = seq - base_seq
    ts = START_TIME + timedelta(seconds=offset_sec)
    print(f"{i:6d} {seq:6d} {b1:4d} {b2:4d} {val:4d}  {ts.strftime('%Y-%m-%d %H:%M:%S')}")

# Step 7: Look for pattern changes — sample every 10000 records
print(f"\n{'='*70}")
print(f"Sample every 10000 records:")
print(f"{'='*70}")
print(f"{'#':>8} {'Seq':>6} {'b1':>4} {'b2':>4} {'Val':>4}  Timestamp")
for i in range(0, len(records), 10000):
    seq, b1, b2, val = records[i]
    offset_sec = seq - base_seq
    ts = START_TIME + timedelta(seconds=offset_sec)
    print(f"{i:8d} {seq:6d} {b1:4d} {b2:4d} {val:4d}  {ts.strftime('%Y-%m-%d %H:%M:%S')}")

# Step 8: Check if b1,b2 form a 16-bit value
print(f"\n{'='*70}")
print(f"Interpreting b1,b2 as little-endian 16-bit:")
print(f"{'='*70}")
b1b2_vals = [struct.unpack("<H", bytes([r[1], r[2]]))[0] for r in records[:30]]
print(f"First 30 b1b2 values: {b1b2_vals}")
b1b2_all = set(struct.unpack("<H", bytes([r[1], r[2]]))[0] for r in records)
print(f"Unique b1b2 values: {len(b1b2_all)}")
if len(b1b2_all) <= 30:
    print(f"  All values: {sorted(b1b2_all)}")

# Step 9: Alternative interpretation - maybe NOT 5-byte records
# Try 4-byte records (seq already part of chunked protocol?)
print(f"\n{'='*70}")
print(f"Alternative: 4-byte records (no per-record sequence)")
print(f"{'='*70}")
rec4_count = len(data) // 4
print(f"Would give {rec4_count} records, remainder {len(data) % 4}")
print(f"First 20 as 4-byte tuples:")
for i in range(20):
    a, b, c, d = data[i*4], data[i*4+1], data[i*4+2], data[i*4+3]
    print(f"  [{a:3d} {b:3d} {c:3d} {d:3d}]  hex=[{a:02x} {b:02x} {c:02x} {d:02x}]")

# Step 10: Check for sub-records with type markers
# Look for 0x01 markers that might delimit records of different types
print(f"\n{'='*70}")
print(f"Byte frequency analysis (first 10000 bytes of payload):")
print(f"{'='*70}")
from collections import Counter
freq = Counter(data[:10000])
for byte_val, count in freq.most_common(20):
    print(f"  0x{byte_val:02x} ({byte_val:3d}): {count:5d} times")

# Step 11: Look for the 0x01 byte that appears at record boundaries in chunks
# From hex dump: offset 0xf4 has `01` between records
print(f"\n{'='*70}")
print(f"Checking for marker bytes at regular intervals:")
print(f"{'='*70}")
# In chunk 0, byte at offset 0xf4 (244 from chunk start, but we stripped seq byte so 243)
# Actually from the raw hex: position 0xf0-0xff:
# 4a 01 1f 11 c8 69 4b 20 11 c8 69 49 21 11 c8 69
# The 01 at position 0xf1 looks like it's between two 5-byte records
# Record before: ...4a  (end of previous)
# Then: 01 1f 11 c8 69 4b  — but that's 6 bytes
# Maybe the record is actually [counter_byte, seq_lo, seq_hi, b1, b2, val] = 6 bytes?

print(f"\nTrying 6-byte records:")
rec6_count = len(data) // 6
print(f"Would give {rec6_count} records, remainder {len(data) % 6}")
for i in range(20):
    r = data[i*6:i*6+6]
    if len(r) == 6:
        print(f"  [{r[0]:3d} {r[1]:3d} {r[2]:3d} {r[3]:3d} {r[4]:3d} {r[5]:3d}]  hex=[{r.hex()}]")

print("\nDone.")
