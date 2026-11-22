"""One fixed AES-128 block for the wire format, not a general cryptography API.

State and round-key bytes are column-major as in FIPS 197. S-boxes are
computed from the field definition rather than taken from the Android binary.
"""

KEY = bytes.fromhex('34522a5b7a6e492c08090a9d8d2a23f8')


def _mul(a, b):
    result = 0
    while b:
        if b & 1:
            result ^= a
        a = ((a << 1) ^ (0x11b if a & 128 else 0)) & 255
        b >>= 1
    return result


def _sbox():
    # 3 generates the nonzero field elements. Inverting 3**i gives 3**(-i).
    powers = [1]
    for _ in range(254):
        powers.append(_mul(powers[-1], 3))
    box = [0x63] * 256
    for i, x in enumerate(powers):
        y = powers[-i]
        affine = y ^ 0x63
        for n in (1, 2, 3, 4):
            affine ^= ((y << n) | (y >> (8 - n))) & 255
        box[x] = affine
    return bytes(box)


_S = _sbox()
_INV = bytes(_S.index(x) for x in range(256))


def _expand(key):
    out = bytearray(key)
    rc = 1
    for index in range(4, 44):
        word = out[-4:]
        if not index % 4:
            word = (word[1:] + word[:1]).translate(_S)
            word[0] ^= rc
            rc = _mul(rc, 2)
        for value in word:
            out.append(out[-16] ^ value)
    return tuple(out[i:i + 16] for i in range(0, 176, 16))


_KEYS = _expand(KEY)


def _xor(state, key):
    return bytes(x ^ y for x, y in zip(state, key, strict=True))


def _shift(state, direction):
    return bytes(state[4 * ((col + direction * row) % 4) + row]
                 for col in range(4) for row in range(4))


def _mix(state, coefficients):
    out = bytearray(16)
    for i in range(0, 16, 4):
        for row in range(4):
            for j, k in enumerate(coefficients):
                out[i + row] ^= _mul(state[i + (row + j) % 4], k)
    return bytes(out)


def block(data: bytes, *, inverse: bool = False) -> bytes:
    """Transform exactly one block; never truncate, pad, or mutate the caller's data."""
    if not isinstance(data, bytes) or len(data) != 16:
        raise ValueError('expected exactly 16 bytes')
    if inverse:
        state = _xor(data, _KEYS[10])
        for i in range(9, -1, -1):
            state = _xor(_shift(state, -1).translate(_INV), _KEYS[i])
            if i:
                state = _mix(state, (14, 11, 13, 9))
        return state
    state = _xor(data, _KEYS[0])
    for i in range(1, 11):
        state = _shift(state.translate(_S), 1)
        if i < 10:
            state = _mix(state, (2, 3, 1, 1))
        state = _xor(state, _KEYS[i])
    return state
