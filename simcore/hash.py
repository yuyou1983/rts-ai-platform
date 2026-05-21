"""FNV-1a 64-bit hash for deterministic state fingerprinting."""
from __future__ import annotations

# FNV-1a 64-bit constants
_FNV_OFFSET = 0xCBF29CE484222325
_FNV_PRIME = 0x00000100000001B3
_MASK64 = 0xFFFFFFFFFFFFFFFF


def fnv1a_64(data: bytes) -> int:
    """Compute FNV-1a 64-bit hash of *data*.

    Args:
        data: Bytes to hash.

    Returns:
        Unsigned 64-bit integer hash value.
    """
    h = _FNV_OFFSET
    for byte in data:
        h ^= byte
        h = (h * _FNV_PRIME) & _MASK64
    return h