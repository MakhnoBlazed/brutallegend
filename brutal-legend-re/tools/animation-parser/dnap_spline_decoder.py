#!/usr/bin/env python3
"""
dnap_spline_decoder.py

Implements the dnap = hkaSplineCompressedAnimation decoder based on:
- FUN_00dd1a00 (per-block per-track header walker)
- FUN_00dd1810/50 (T/S and R component encoding dispatch)
- DAT_00e71108 (alignment table) + DAT_00e71120 (size table)
- FUN_00dd14d0 (byte-swap / cursor advance helper)

Per-track header layout:
  Quat tracks: 4 bytes each = [flags, T_sub, R_sub, S_sub]
    flags & 0x03         → trans encoding type (0-3)
    (flags >> 2) & 0x0F  → rot   encoding type (0-5 used)
    flags >> 6           → scale encoding type (0-3)
  Float tracks: 1 byte each
    bVar1 & 0xF9         → component flags
    (bVar1 >> 1) & 0x03  → encoding type

Rotation encoding types (from DAT_00e71108 / DAT_00e71120):
  type | align | size | name
   0   |   4   |   4  | Smallest3-32 / BitPacked  (4 bytes)
   1   |   1   |   5  | Smallest3-40              (5 bytes)
   2   |   2   |   6  | Smallest3-48              (6 bytes)
   3   |   1   |   3  | Smallest3-24 (custom)     (3 bytes)
   4   |   2   |   2  | Half quaternion           (2 bytes)
   5   |   4   |  16  | Full f32 quaternion       (16 bytes, no compression)
"""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass
from typing import Optional, Tuple

INV_SQRT2 = 1.0 / math.sqrt(2.0)

# Per-encoding-type tables (extracted from BL.exe's DAT_00e71108 / DAT_00e71120)
ROT_ALIGN = [4, 1, 2, 1, 2, 4]      # bytes alignment per encoding type
ROT_SIZE  = [4, 5, 6, 3, 2, 16]     # bytes per encoded value per encoding type


# -----------------------------------------------------------------------------
# Quaternion decoders — one per encoding type
# -----------------------------------------------------------------------------
def decode_quat_smallest3_48(data: bytes, off: int) -> Tuple[float, float, float, float]:
    """6-byte smallest3 quaternion: 2-bit largest-component index + 3×15-bit values.
    Already validated in b20_horse_anim_parser.py."""
    v = int.from_bytes(data[off:off + 6], "little")
    largest_idx = v & 0x3
    a = (v >> 2)  & 0x7FFF
    b = (v >> 17) & 0x7FFF
    c = (v >> 32) & 0x7FFF

    def deq(r: int) -> float:
        return r / 32767.0 * (2.0 * INV_SQRT2) - INV_SQRT2

    a_f, b_f, c_f = deq(a), deq(b), deq(c)
    s = 1.0 - a_f * a_f - b_f * b_f - c_f * c_f
    d_f = math.sqrt(s) if s > 0 else 0.0
    out = [0.0, 0.0, 0.0, 0.0]
    others = [i for i in range(4) if i != largest_idx]
    out[others[0]], out[others[1]], out[others[2]] = a_f, b_f, c_f
    out[largest_idx] = d_f
    return tuple(out)


def decode_quat_smallest3_40(data: bytes, off: int) -> Tuple[float, float, float, float]:
    """5-byte smallest3 quaternion: 2-bit largest + 3×12-bit values + 2 bits unused."""
    v = int.from_bytes(data[off:off + 5], "little")
    largest_idx = v & 0x3
    a = (v >> 2)  & 0xFFF
    b = (v >> 14) & 0xFFF
    c = (v >> 26) & 0xFFF

    def deq(r: int) -> float:
        return r / 4095.0 * (2.0 * INV_SQRT2) - INV_SQRT2

    a_f, b_f, c_f = deq(a), deq(b), deq(c)
    s = 1.0 - a_f * a_f - b_f * b_f - c_f * c_f
    d_f = math.sqrt(s) if s > 0 else 0.0
    out = [0.0, 0.0, 0.0, 0.0]
    others = [i for i in range(4) if i != largest_idx]
    out[others[0]], out[others[1]], out[others[2]] = a_f, b_f, c_f
    out[largest_idx] = d_f
    return tuple(out)


def decode_quat_smallest3_32(data: bytes, off: int) -> Tuple[float, float, float, float]:
    """4-byte smallest3 quaternion: 2-bit largest + 3×10-bit values."""
    v = int.from_bytes(data[off:off + 4], "little")
    largest_idx = v & 0x3
    a = (v >> 2)  & 0x3FF
    b = (v >> 12) & 0x3FF
    c = (v >> 22) & 0x3FF

    def deq(r: int) -> float:
        return r / 1023.0 * (2.0 * INV_SQRT2) - INV_SQRT2

    a_f, b_f, c_f = deq(a), deq(b), deq(c)
    s = 1.0 - a_f * a_f - b_f * b_f - c_f * c_f
    d_f = math.sqrt(s) if s > 0 else 0.0
    out = [0.0, 0.0, 0.0, 0.0]
    others = [i for i in range(4) if i != largest_idx]
    out[others[0]], out[others[1]], out[others[2]] = a_f, b_f, c_f
    out[largest_idx] = d_f
    return tuple(out)


def decode_quat_smallest3_24(data: bytes, off: int) -> Tuple[float, float, float, float]:
    """3-byte smallest3 quaternion: 2-bit largest + 3×7-bit signed values + 1 bit unused (or sign).
    Highly approximate — verify against actual data."""
    v = int.from_bytes(data[off:off + 3], "little")
    largest_idx = v & 0x3
    a = (v >> 2)  & 0x7F
    b = (v >> 9)  & 0x7F
    c = (v >> 16) & 0x7F

    def deq(r: int) -> float:
        return r / 127.0 * (2.0 * INV_SQRT2) - INV_SQRT2

    a_f, b_f, c_f = deq(a), deq(b), deq(c)
    s = 1.0 - a_f * a_f - b_f * b_f - c_f * c_f
    d_f = math.sqrt(s) if s > 0 else 0.0
    out = [0.0, 0.0, 0.0, 0.0]
    others = [i for i in range(4) if i != largest_idx]
    out[others[0]], out[others[1]], out[others[2]] = a_f, b_f, c_f
    out[largest_idx] = d_f
    return tuple(out)


def decode_quat_half(data: bytes, off: int) -> Tuple[float, float, float, float]:
    """2-byte 'half' quaternion. Implementation guess — likely 4×4-bit packed.
    May need refinement from FUN_00dd0680's [4] entry."""
    v = struct.unpack_from("<H", data, off)[0]
    # Tentative interpretation: 4 components × 4 bits each
    qx = ((v >> 0)  & 0x0F) / 7.5 - 1.0
    qy = ((v >> 4)  & 0x0F) / 7.5 - 1.0
    qz = ((v >> 8)  & 0x0F) / 7.5 - 1.0
    qw = ((v >> 12) & 0x0F) / 7.5 - 1.0
    n = math.sqrt(qx*qx + qy*qy + qz*qz + qw*qw) or 1.0
    return (qx/n, qy/n, qz/n, qw/n)


def decode_quat_uncompressed(data: bytes, off: int) -> Tuple[float, float, float, float]:
    """16-byte full f32 quaternion (no compression)."""
    return struct.unpack_from("<ffff", data, off)


# -----------------------------------------------------------------------------
# Encoding-type dispatch — the 6 entries of PTR_LAB_00f73838
# -----------------------------------------------------------------------------
QUAT_DECODERS = [
    decode_quat_smallest3_32,   # type 0: 4 bytes
    decode_quat_smallest3_40,   # type 1: 5 bytes
    decode_quat_smallest3_48,   # type 2: 6 bytes (most common — what our parser already had)
    decode_quat_smallest3_24,   # type 3: 3 bytes
    decode_quat_half,           # type 4: 2 bytes
    decode_quat_uncompressed,   # type 5: 16 bytes
]


def align_cursor(cursor: int, alignment: int) -> int:
    """Round cursor up to alignment boundary (matches FUN_00dd06a0 prologue)."""
    return (cursor + alignment - 1) & ~(alignment - 1)


# -----------------------------------------------------------------------------
# Per-track header parsers
# -----------------------------------------------------------------------------
@dataclass
class QuatTrackHeader:
    """4-byte header per quaternion track (T+R+S)."""
    flags: int          # byte[0] = packed encoding selectors
    trans_subflags: int # byte[1]
    rot_subflags: int   # byte[2]
    scale_subflags: int # byte[3]

    @property
    def trans_encoding(self) -> int:
        return self.flags & 0x03

    @property
    def rot_encoding(self) -> int:
        return (self.flags >> 2) & 0x0F

    @property
    def scale_encoding(self) -> int:
        return (self.flags >> 6) & 0x03


@dataclass
class FloatTrackHeader:
    """1-byte header per scalar float track."""
    raw: int

    @property
    def comp_flags(self) -> int:
        return self.raw & 0xF9

    @property
    def encoding(self) -> int:
        return (self.raw >> 1) & 0x03


def parse_quat_track_headers(data: bytes, off: int, num_quat_tracks: int) -> list:
    """Read num_quat_tracks × 4-byte headers starting at off."""
    headers = []
    for i in range(num_quat_tracks):
        p = off + i * 4
        if p + 4 > len(data):
            break
        headers.append(QuatTrackHeader(
            flags=data[p],
            trans_subflags=data[p + 1],
            rot_subflags=data[p + 2],
            scale_subflags=data[p + 3],
        ))
    return headers


def parse_float_track_headers(data: bytes, off: int, num_float_tracks: int) -> list:
    """Read num_float_tracks × 1-byte headers starting at off."""
    return [FloatTrackHeader(raw=data[off + i]) for i in range(num_float_tracks)
            if off + i < len(data)]


# -----------------------------------------------------------------------------
# Stream layout calculator (mirrors FUN_00dd1a00 / FUN_00dd06a0 size pass)
# -----------------------------------------------------------------------------
def compute_block_data_size(
    quat_headers: list,
    float_headers: list,
    num_knots_in_block: int,
) -> int:
    """Compute the byte size of all per-track encoded data in one block.

    Per FUN_00dd06a0:
        cursor = align(cursor, ROT_ALIGN[encoding_type])
        if (flags & 0xF0) == 0:           # static rotation (1 sample)
            cursor += ROT_SIZE[encoding_type]
        else:                              # dynamic per-knot
            for k in range(num_knots + 1):
                cursor += ROT_SIZE[encoding_type]
    """
    cursor = 0

    for hdr in quat_headers:
        # Translation (3 components)
        for axis in range(3):
            t_bit = (hdr.trans_subflags >> axis) & 1
            t_hi  = (hdr.trans_subflags >> (axis + 4)) & 1
            if t_bit == 0:
                continue
            if t_hi == 0:
                cursor += 4   # uncompressed f32
            else:
                cursor += 8 + num_knots_in_block  # 2× f32 range + 1 byte/knot

        # Rotation
        rot_enc = hdr.rot_encoding
        if rot_enc < len(ROT_ALIGN):
            cursor = align_cursor(cursor, ROT_ALIGN[rot_enc])
            if (hdr.rot_subflags & 0xF0) == 0:
                cursor += ROT_SIZE[rot_enc]   # static rotation
            else:
                cursor += ROT_SIZE[rot_enc] * (num_knots_in_block + 1)

        # Scale (3 components, same logic as translation)
        for axis in range(3):
            s_bit = (hdr.scale_subflags >> axis) & 1
            s_hi  = (hdr.scale_subflags >> (axis + 4)) & 1
            if s_bit == 0:
                continue
            if s_hi == 0:
                cursor += 4
            else:
                cursor += 8 + num_knots_in_block

    for hdr in float_headers:
        # Float tracks: similar but only 1 component
        if (hdr.comp_flags & 0x01) != 0:
            cursor += 4  # at minimum one f32

    return cursor


# -----------------------------------------------------------------------------
# Sample-time interpolation (mirrors FUN_00dd4680)
# -----------------------------------------------------------------------------
def time_to_block_local(
    time_seconds: float,
    block_duration: float,    # this[+0x34]
    inv_block_duration: float, # this[+0x38]
    knots_per_block: int,     # this[+0x2c]
    total_blocks: int,        # this[+0x28]
) -> Tuple[int, float, int]:
    """Convert global time to (block_idx, local_time, sub_frame_idx).
    Mirrors FUN_00dd4680.
    """
    block_idx = int(time_seconds * inv_block_duration)
    block_idx = max(0, min(block_idx, total_blocks - 1))
    local_time = time_seconds - block_duration * block_idx
    sub_frame = int(round(local_time * inv_block_duration * (knots_per_block - 1)))
    return block_idx, local_time, sub_frame


# -----------------------------------------------------------------------------
# Top-level: decode one frame from a dnap buffer
# -----------------------------------------------------------------------------
def decode_dnap_frame(
    dnap_bytes: bytes,
    frame_index: int,
    num_quat_tracks: int,
    num_float_tracks: int,
    block_offsets: list,        # u32[num_blocks] from runtime struct +0x40
    knots_per_block: int,       # this[+0x2c]
    block_data_offset: int,     # this[+0x30] — offset to data after track headers
    base_data_cursor: int = 0x68,  # most dnap files store data after a 0x68-byte header
) -> Optional[dict]:
    """Best-effort frame decoder. Layout assumptions are based on
    the static analysis of FUN_00dd1a00/06a0/14d0 plus DAT_00e71108/120.

    NOTE: This is a STARTING POINT. The exact block-offset table location
    and base data cursor may differ in real dnap files — these need
    empirical validation against b20_horse animations.
    """
    if not block_offsets:
        return None
    block_idx = frame_index // knots_per_block
    if block_idx >= len(block_offsets):
        return None

    block_start = base_data_cursor + block_offsets[block_idx]
    quat_headers = parse_quat_track_headers(
        dnap_bytes, block_start, num_quat_tracks)
    float_headers = parse_float_track_headers(
        dnap_bytes,
        block_start + num_quat_tracks * 4,
        num_float_tracks)

    return {
        "block_idx": block_idx,
        "block_start": block_start,
        "frame_in_block": frame_index % knots_per_block,
        "quat_headers": [
            {
                "flags_hex": f"0x{h.flags:02X}",
                "trans_encoding": h.trans_encoding,
                "rot_encoding": h.rot_encoding,
                "scale_encoding": h.scale_encoding,
                "T_sub": f"0x{h.trans_subflags:02X}",
                "R_sub": f"0x{h.rot_subflags:02X}",
                "S_sub": f"0x{h.scale_subflags:02X}",
            }
            for h in quat_headers
        ],
        "float_headers": [
            {
                "raw": f"0x{h.raw:02X}",
                "encoding": h.encoding,
                "comp_flags": h.comp_flags,
            }
            for h in float_headers
        ],
        "estimated_block_size": compute_block_data_size(
            quat_headers, float_headers, knots_per_block),
    }


# -----------------------------------------------------------------------------
# Smoke test
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    print("Quat decoder smoke test (smallest3-48):")
    test_bytes = bytes.fromhex("c2eb05bb61c17db900")
    q = decode_quat_smallest3_48(test_bytes, 0)
    print(f"  decoded: {q}, magnitude={math.sqrt(sum(x*x for x in q)):.6f}")

    print("\nROT_SIZE table:", ROT_SIZE)
    print("ROT_ALIGN table:", ROT_ALIGN)
    print("\nDecoder ready. Integrate with b20_horse_anim_parser.py to per-frame decode.")
