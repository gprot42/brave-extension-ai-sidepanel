"""Exact Python port of Gadgetbridge's ECDH_B163.java.

Line-by-line translation of the GF(2^163) / NIST B-163 ECDH implementation
from https://codeberg.org/Freeyourgadget/Gadgetbridge (tiny-ECDH-c port).
All int[] are 6 x 32-bit words, little-endian word order.
Python ints are masked to 32 bits where needed (Java int is signed 32-bit).
"""

import os
import struct

CURVE_DEGREE = 163
ECC_PRV_KEY_SIZE = 24
ECC_PUB_KEY_SIZE = 2 * ECC_PRV_KEY_SIZE

BITVEC_MARGIN = 3
BITVEC_NBITS = CURVE_DEGREE + BITVEC_MARGIN  # 166
BITVEC_NWORDS = (BITVEC_NBITS + 31) // 32     # 6
BITVEC_NBYTES = 4 * BITVEC_NWORDS              # 24

MASK32 = 0xFFFFFFFF

# NIST B-163 curve parameters
polynomial  = [0x000000c9, 0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000008]
coeff_b     = [0x4a3205fd, 0x512f7874, 0x1481eb10, 0xb8c953ca, 0x0a601907, 0x00000002]
base_x      = [0xe8343e36, 0xd4994637, 0xa0991168, 0x86a2d57e, 0xf0eba162, 0x00000003]
base_y      = [0x797324f1, 0xb11c5c0c, 0xa2cdd545, 0x71a0094f, 0xd51fbc6c, 0x00000000]
base_order  = [0xa4234c33, 0x77e70c12, 0x000292fe, 0x00000000, 0x00000000, 0x00000004]


# ── Byte ↔ int[] conversion (matches Java's bytes_to_int / ints_to_bytes) ──

def bytes_to_int(b: bytes, offset: int = 0) -> list:
    value = [0] * BITVEC_NWORDS
    bp = offset
    for i in range(BITVEC_NWORDS):
        value[i] = (
            (b[bp] & 0xFF)
            | ((b[bp + 1] & 0xFF) << 8)
            | ((b[bp + 2] & 0xFF) << 16)
            | ((b[bp + 3] & 0xFF) << 24)
        ) & MASK32
        bp += 4
    return value


def ints_to_bytes_into(buf: bytearray, ints: list, offset: int):
    bp = offset
    for i in range(BITVEC_NWORDS):
        v = ints[i] & MASK32
        buf[bp] = v & 0xFF
        buf[bp + 1] = (v >> 8) & 0xFF
        buf[bp + 2] = (v >> 16) & 0xFF
        buf[bp + 3] = (v >> 24) & 0xFF
        bp += 4


def ints_to_bytes(ints: list) -> bytes:
    buf = bytearray(BITVEC_NBYTES)
    ints_to_bytes_into(buf, ints, 0)
    return bytes(buf)


# ── Bit vector primitives ──

def bitvec_get_bit(x, idx):
    return int(((x[idx // 32] & MASK32) >> (idx & 31)) & 1)


def bitvec_clr_bit(x, idx):
    x[idx // 32] = (x[idx // 32] & ~(1 << (idx & 31))) & MASK32


def bitvec_copy(dst, src):
    """Copy src into dst (in-place). dst and src are int[6]."""
    for i in range(BITVEC_NWORDS):
        dst[i] = src[i]


def bitvec_swap(x, y):
    tmp = [0] * BITVEC_NWORDS
    bitvec_copy(tmp, x)
    bitvec_copy(x, y)
    bitvec_copy(y, tmp)


def bitvec_equal(x, y):
    for i in range(BITVEC_NWORDS):
        if x[i] != y[i]:
            return False
    return True


def bitvec_set_zero(x):
    for i in range(BITVEC_NWORDS):
        x[i] = 0


def bitvec_is_zero(x):
    i = 0
    while i < BITVEC_NWORDS:
        if x[i] != 0:
            break
        i += 1
    return i == BITVEC_NWORDS


def bitvec_degree(x):
    """Return the number of the highest one-bit + 1."""
    i = BITVEC_NWORDS * 32
    y = BITVEC_NWORDS
    while i > 0 and x[y - 1] == 0:
        y -= 1
        i -= 32
    if i != 0:
        u32mask = 1 << 31
        while ((x[y - 1]) & u32mask) == 0:
            u32mask = (u32mask & MASK32) >> 1
            i -= 1
    return i


def bitvec_lshift(x, y, nbits):
    """Left-shift: x = y << nbits."""
    nwords = nbits // 32
    for i in range(nwords):
        x[i] = 0
    j = 0
    i = nwords
    while i < BITVEC_NWORDS:
        x[i] = y[j]
        i += 1
        j += 1
    nbits &= 31
    if nbits != 0:
        for i in range(BITVEC_NWORDS - 1, 0, -1):
            x[i] = ((x[i] << nbits) | ((x[i - 1] & MASK32) >> (32 - nbits))) & MASK32
        x[0] = (x[0] << nbits) & MASK32


# ── GF(2^163) field arithmetic ──

def gf2field_set_one(x):
    x[0] = 1
    for i in range(1, BITVEC_NWORDS):
        x[i] = 0


def gf2field_is_one(x):
    if x[0] != 1:
        return False
    for i in range(1, BITVEC_NWORDS):
        if x[i] != 0:
            return False
    return True


def gf2field_add(z, x, y):
    """z = x + y in GF(2) (XOR). Modifies z in place."""
    for i in range(BITVEC_NWORDS):
        z[i] = (x[i] ^ y[i]) & MASK32


def gf2field_inc(x):
    x[0] ^= 1


def gf2field_mul(z, x, y):
    """z = x * y in GF(2^163). z must not alias y."""
    tmp = [0] * BITVEC_NWORDS
    bitvec_copy(tmp, x)

    if bitvec_get_bit(y, 0) != 0:
        bitvec_copy(z, x)
    else:
        bitvec_set_zero(z)

    for i in range(1, CURVE_DEGREE):
        bitvec_lshift(tmp, tmp, 1)
        if bitvec_get_bit(tmp, CURVE_DEGREE) != 0:
            gf2field_add(tmp, tmp, polynomial)
        if bitvec_get_bit(y, i) != 0:
            gf2field_add(z, z, tmp)


def gf2field_inv(z, x):
    """z = 1/x in GF(2^163)."""
    u = [0] * BITVEC_NWORDS
    v = [0] * BITVEC_NWORDS
    g = [0] * BITVEC_NWORDS
    h = [0] * BITVEC_NWORDS

    bitvec_copy(u, x)
    bitvec_copy(v, polynomial)
    bitvec_set_zero(g)
    gf2field_set_one(z)

    while not gf2field_is_one(u):
        i = bitvec_degree(u) - bitvec_degree(v)
        if i < 0:
            bitvec_swap(u, v)
            bitvec_swap(g, z)
            i = -i
        bitvec_lshift(h, v, i)
        gf2field_add(u, u, h)
        bitvec_lshift(h, g, i)
        gf2field_add(z, z, h)


# ── Elliptic curve point operations ──

def gf2point_copy(x1, y1, x2, y2):
    bitvec_copy(x1, x2)
    bitvec_copy(y1, y2)


def gf2point_set_zero(x, y):
    bitvec_set_zero(x)
    bitvec_set_zero(y)


def gf2point_is_zero(x, y):
    return bitvec_is_zero(x) and bitvec_is_zero(y)


def gf2point_double(x, y):
    """Double point (x, y) in place."""
    if bitvec_is_zero(x):
        bitvec_set_zero(y)
    else:
        l = [0] * BITVEC_NWORDS
        gf2field_inv(l, x)
        gf2field_mul(l, l, y)
        gf2field_add(l, l, x)
        gf2field_mul(y, x, x)
        gf2field_mul(x, l, l)
        gf2field_inc(l)
        gf2field_add(x, x, l)
        gf2field_mul(l, l, x)
        gf2field_add(y, y, l)


def gf2point_add(x1, y1, x2, y2):
    """Add (x2, y2) to (x1, y1) in place."""
    if not gf2point_is_zero(x2, y2):
        if gf2point_is_zero(x1, y1):
            gf2point_copy(x1, y1, x2, y2)
        else:
            if bitvec_equal(x1, x2):
                if bitvec_equal(y1, y2):
                    gf2point_double(x1, y1)
                else:
                    gf2point_set_zero(x1, y1)
            else:
                a = [0] * BITVEC_NWORDS
                b = [0] * BITVEC_NWORDS
                c = [0] * BITVEC_NWORDS
                d = [0] * BITVEC_NWORDS

                gf2field_add(a, y1, y2)
                gf2field_add(b, x1, x2)
                gf2field_inv(c, b)
                gf2field_mul(c, c, a)
                gf2field_mul(d, c, c)
                gf2field_add(d, d, c)
                gf2field_add(d, d, b)
                gf2field_inc(d)
                gf2field_add(x1, x1, d)
                gf2field_mul(a, x1, c)
                gf2field_add(a, a, d)
                gf2field_add(y1, y1, a)
                bitvec_copy(x1, d)


def gf2point_mul(x, y, exp):
    """Scalar multiply: (x, y) = exp * (x, y). Modifies x, y in place."""
    tmpx = [0] * BITVEC_NWORDS
    tmpy = [0] * BITVEC_NWORDS

    nbits = bitvec_degree(exp)
    gf2point_set_zero(tmpx, tmpy)

    for i in range(nbits - 1, -1, -1):
        gf2point_double(tmpx, tmpy)
        if bitvec_get_bit(exp, i) != 0:
            gf2point_add(tmpx, tmpy, x, y)

    gf2point_copy(x, y, tmpx, tmpy)


def gf2point_on_curve(x, y):
    """Check if y^2 + x*y = x^3 + a*x^2 + b."""
    a = [0] * BITVEC_NWORDS
    b = [0] * BITVEC_NWORDS

    if gf2point_is_zero(x, y):
        return False

    gf2field_mul(a, x, x)       # a = x^2
    gf2field_mul(b, a, x)       # b = x^3
    gf2field_add(a, a, b)       # a = x^2 + x^3
    gf2field_add(a, a, coeff_b) # a = x^2 + x^3 + b
    gf2field_mul(b, y, y)       # b = y^2
    gf2field_add(a, a, b)       # a = x^2 + x^3 + b + y^2
    gf2field_mul(b, x, y)       # b = x*y
    return bitvec_equal(a, b)   # x^2 + x^3 + b + y^2 == x*y


# ── ECDH key operations ──

def ecdh_generate_keys(public_key: bytearray, private_key: bytes) -> bool:
    """Generate public key from private key. Matches Java signature."""
    private_key_int32 = bytes_to_int(private_key, 0)
    public_key_int32_1 = bytes_to_int(public_key, 0)
    public_key_int32_2 = bytes_to_int(public_key, BITVEC_NBYTES)

    gf2point_copy(public_key_int32_1, public_key_int32_2, base_x, base_y)

    if bitvec_degree(private_key_int32) < (CURVE_DEGREE // 2):
        return False

    nbits = bitvec_degree(base_order)
    for i in range(nbits - 1, BITVEC_NWORDS * 32):
        bitvec_clr_bit(private_key_int32, i)

    gf2point_mul(public_key_int32_1, public_key_int32_2, private_key_int32)

    ints_to_bytes_into(public_key, public_key_int32_1, 0)
    ints_to_bytes_into(public_key, public_key_int32_2, BITVEC_NBYTES)
    return True


def ecdh_shared_secret(private_key: bytes, others_pub: bytes, output: bytearray) -> bool:
    """Compute ECDH shared secret. Matches Java signature."""
    private_key_int32 = bytes_to_int(private_key, 0)
    others_pub_int32_1 = bytes_to_int(others_pub, 0)
    others_pub_int32_2 = bytes_to_int(others_pub, BITVEC_NBYTES)

    if (not gf2point_is_zero(others_pub_int32_1, others_pub_int32_2)
            and gf2point_on_curve(others_pub_int32_1, others_pub_int32_2)):
        for i in range(BITVEC_NBYTES * 2):
            output[i] = others_pub[i]

        nbits = bitvec_degree(base_order)
        for i in range(nbits - 1, BITVEC_NWORDS * 32):
            bitvec_clr_bit(private_key_int32, i)

        output_int32_1 = bytes_to_int(output, 0)
        output_int32_2 = bytes_to_int(output, BITVEC_NBYTES)

        gf2point_mul(output_int32_1, output_int32_2, private_key_int32)

        ints_to_bytes_into(output, output_int32_1, 0)
        ints_to_bytes_into(output, output_int32_2, BITVEC_NBYTES)
        return True
    else:
        return False


# ── Convenience wrappers (match Gadgetbridge's static helpers) ──

def ecdh_generate_public(private_ec: bytes) -> bytes:
    pub_key = bytearray(ECC_PUB_KEY_SIZE)
    if ecdh_generate_keys(pub_key, private_ec):
        return bytes(pub_key)
    return None


def ecdh_generate_shared(private_ec: bytes, remote_public_ec: bytes) -> bytes:
    shared_key = bytearray(ECC_PUB_KEY_SIZE)
    if ecdh_shared_secret(private_ec, remote_public_ec, shared_key):
        return bytes(shared_key)
    return None


def generate_private_key() -> bytes:
    """Generate a random private key with sufficient entropy."""
    while True:
        key = os.urandom(ECC_PRV_KEY_SIZE)
        words = bytes_to_int(key)
        if bitvec_degree(words) >= (CURVE_DEGREE // 2):
            nbits = bitvec_degree(base_order)
            for i in range(nbits - 1, BITVEC_NWORDS * 32):
                bitvec_clr_bit(words, i)
            return ints_to_bytes(words)


# ── Self-test ──

if __name__ == "__main__":
    print("Testing ECDH_B163 port...")

    priv1 = generate_private_key()
    pub1 = ecdh_generate_public(priv1)
    print(f"Key A priv: {priv1.hex()}")
    print(f"Key A pub:  {pub1.hex()}")

    priv2 = generate_private_key()
    pub2 = ecdh_generate_public(priv2)
    print(f"Key B priv: {priv2.hex()}")
    print(f"Key B pub:  {pub2.hex()}")

    shared1 = ecdh_generate_shared(priv1, pub2)
    shared2 = ecdh_generate_shared(priv2, pub1)
    print(f"Shared A->B: {shared1.hex()}")
    print(f"Shared B->A: {shared2.hex()}")
    print(f"Match: {shared1 == shared2}")

    if shared1 != shared2:
        print("FAIL: Shared secrets do not match!")
        exit(1)
    else:
        print("PASS: ECDH key agreement works correctly.")
