#!/usr/bin/env python3
"""
b20_horse_anim_parser.py

Parses Brutal Legend animation assets for the b20_horse character. Handles:
  .Rig + .Rig.Header              -> skeleton (bones, parents, bind pose)
  .AnimResource + .AnimResource.header -> compressed animation tracks
  .Stance / .ComboPose / .ComboAnim    -> property text files
  .Mesh + .Mesh.header             -> light header decode (for completeness)
  .PhysicsRigidBody                -> light header decode

Output: per-asset JSON next to each input file (under an output dir),
plus a top-level summary.json.

Format notes inferred from Ghidra (FUN_00dcca40 -> StDecompressD,
FUN_00dcc100 / FUN_00dd6ad0 / FUN_00dd7b00) and the dnap section layout:

  AnimResource header (offset / type / meaning)
    0x00  4s    magic 'dnap'
    0x04  f32   period_seconds  (frames_per_period / fps)
    0x08  f32   fps
    0x0C  u16   total_frames
    0x0E  u16   version (0=breathe-style, 2=trot-style)
    0x10  u16   frames_per_period (loop length in frames)
    0x12  u16   num_tracks
    0x14  u16   pad / unused
    0x16  u16   num_blocks
    0x18..0x40  per-anim metadata (4x u32 sentinel 0xC5F17C5C bbox markers,
                                   block layout hints)
    0x40  u32[8] section sizes secs[0..7]
    0x60  u32   pad
    0x64  u32   pad
    0x68  u32   first-block flag
    0x6C  u16[] track->bone remap (length = (secs[2]-0x6C)//2)
    secs[2]              start of compressed payload
    secs[2] .. secs[2]+secs[1]   reference-pose quaternions, smallest3-48
                                 (6 B each). The sentinel value 5C 7C F1 C5
                                 in the middle bytes marks a "no quat" slot.
    after that            per-block rotation/translation bitstreams
                          (sizes given by secs[3..6] alternating rot/trans)

  AnimResource.header (sidecar)
    0x00  u32   version (=1)
    0x04  u32   hash1 (rig hash)
    0x08  u32   hash2 (rig hash)
    0x0C  u8    num_skel (animated-bone count)
    0x0D  u8    pad
    0x0E  u8    pad
    0x0F  u8    num_blocks (matches dnap)
    0x10  u8[]  animated bone indices (terminator: byte >= 0x80)
    next  f32   duration_seconds
    next  f32   blend / unused
    next  u32   pad
    'vena' marker + u32 size + ASCII event list + 'mina' tail

The smallest3-48 quaternion encoder packs 3 components in 15 bits each plus
2 bits identifying the largest (omitted) component. The largest component is
recovered as sqrt(1 - a^2 - b^2 - c^2). This corresponds to the
Anim::kACT_Smallest3_48 compression type from BrutalLegend.exe's RTTI.
"""

from __future__ import annotations

import json
import math
import os
import struct
import sys
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Tuple

# -----------------------------------------------------------------------------
# Paths
# -----------------------------------------------------------------------------
B20_DIR = (
    r"D:\SteamLibrary\steamapps\common\BrutalLegend\DoubleFineModTool"
    r"\unpacked\characters\quadrupeds\b20_horse"
)
DEFAULT_OUT = r"E:\ghidra_export\b20_horse_parsed"

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
INV_SQRT2 = 1.0 / math.sqrt(2.0)
SENTINEL_MID = b"\xF1\xC5"  # quat slot is "no rotation"


def u8(b: bytes, off: int) -> int:
    return b[off]


def u16(b: bytes, off: int) -> int:
    return struct.unpack_from("<H", b, off)[0]


def u32(b: bytes, off: int) -> int:
    return struct.unpack_from("<I", b, off)[0]


def f32(b: bytes, off: int) -> float:
    return struct.unpack_from("<f", b, off)[0]


def vec3(b: bytes, off: int) -> Tuple[float, float, float]:
    return struct.unpack_from("<fff", b, off)


def vec4(b: bytes, off: int) -> Tuple[float, float, float, float]:
    return struct.unpack_from("<ffff", b, off)


def qnorm(q: Tuple[float, float, float, float]) -> Tuple[float, float, float, float]:
    m = math.sqrt(sum(x * x for x in q))
    return tuple(x / m for x in q) if m > 1e-10 else (0.0, 0.0, 0.0, 1.0)


def is_quat_sentinel(b6: bytes) -> bool:
    return len(b6) == 6 and b6[2:4] == SENTINEL_MID


def decode_smallest3_48(b6: bytes) -> Optional[Tuple[float, float, float, float]]:
    """Decode a 6-byte smallest3-48 quaternion. None if the slot is sentinel."""
    if is_quat_sentinel(b6):
        return None
    v = int.from_bytes(b6, "little")
    largest_idx = v & 0x3
    a_raw = (v >> 2) & 0x7FFF
    b_raw = (v >> 17) & 0x7FFF
    c_raw = (v >> 32) & 0x7FFF

    def deq(r: int) -> float:
        return r / 32767.0 * (2.0 * INV_SQRT2) - INV_SQRT2

    a, b_, c = deq(a_raw), deq(b_raw), deq(c_raw)
    s = 1.0 - a * a - b_ * b_ - c * c
    d = math.sqrt(s) if s > 0.0 else 0.0
    comps = [0.0, 0.0, 0.0, 0.0]
    others = [i for i in range(4) if i != largest_idx]
    comps[others[0]] = a
    comps[others[1]] = b_
    comps[others[2]] = c
    comps[largest_idx] = d
    return qnorm(tuple(comps))


# -----------------------------------------------------------------------------
# Bit-packed stream decoder (reverse-engineered from
# FUN_00dde3c0 / FUN_00dde310 / FUN_00dddf80 / FUN_00dd6a30 / FUN_00dd7b00)
#
# Each compressed float stream in a dnap block is encoded as:
#   [u8 bits_per_sample][u8 prefix_count][u16 _pad]
#   [f32 scale][f32 base]
#   [f32 prefix_count uncompressed samples]
#   [bit-packed (num_samples - prefix_count) samples at bits_per_sample each]
#
# Dequantization formula:  out = (sample + 0.5) * scale / 2^bits + base
# (the +0.5 is bin-centering — confirmed by FUN_00dde3c0)
#
# After dequantization, FUN_00dde310 runs a prefix-sum (delta-decode) pass:
#   values[i] += values[i-1]   for i >= 1
# turning a stream of [base_value, d1, d2, d3, ...] into absolute samples.
#
# Each track has a 16-bit encoding mask (per FUN_00dd6a30 / FUN_00dd7b00):
#   bits  0-1  trans_skip   (==2 → write zero translation, skip 3 reads)
#   bits  2-3  rot_skip     (==8 → write identity quat, skip 4 reads)
#   bits  4-5  scale_skip   (==0x20 → write unit scale, skip 3 reads)
#   bit  6     Tz src       (0 = dynamic stream, 1 = static stream)
#   bit  7     Ty src
#   bit  8     Tx src
#   bit  9     Qw src       (W = ±2.0 sentinel triggers smallest3 reconstruction)
#   bit 10     Qz src
#   bit 11     Qy src
#   bit 12     Qx src
#   bit 13     Sz src
#   bit 14     Sy src
#   bit 15     Sx src
# -----------------------------------------------------------------------------

QUANT_SCALE = [1.0 / (1 << n) if n > 0 else 1.0 for n in range(33)]


@dataclass
class TrackQuant:
    """Header for one bit-packed float stream."""
    bits_per_sample: int
    prefix_count: int
    scale: float
    base: float

    def is_plausible(self) -> bool:
        return (
            0 < self.bits_per_sample <= 32
            and 0 <= self.prefix_count <= 256
            and math.isfinite(self.scale)
            and math.isfinite(self.base)
            and abs(self.scale) < 1e6
            and abs(self.base) < 1e6
        )


def stream_byte_size(num_samples: int, mask: TrackQuant) -> int:
    """Mirrors FUN_00dddf80 — bytes consumed by one stream."""
    if num_samples <= mask.prefix_count:
        return num_samples * 4
    packed = num_samples - mask.prefix_count
    return mask.prefix_count * 4 + (packed * mask.bits_per_sample + 7) // 8


def parse_track_quant(b: bytes, off: int) -> Optional[TrackQuant]:
    """Try to read a 12-byte TrackQuant header at off."""
    if off + 12 > len(b):
        return None
    bits = b[off]
    prefix = b[off + 1]
    try:
        scale = struct.unpack_from("<f", b, off + 4)[0]
        base = struct.unpack_from("<f", b, off + 8)[0]
    except struct.error:
        return None
    return TrackQuant(bits, prefix, scale, base)


def decode_bit_packed_stream(
    data: bytes, off: int, num_samples: int, mask: TrackQuant
) -> Tuple[List[float], int]:
    """Decode a single bit-packed float stream. Returns (values, bytes_consumed).

    Mirrors FUN_00dde3c0 + FUN_00dde310:
      - first `prefix_count` samples are uncompressed f32;
      - remaining samples are `bits_per_sample` bits each, dequantized as
            (sample + 0.5) * scale / 2^bits + base
      - then the whole array is prefix-summed (delta-decoded).
    """
    out: List[float] = []
    p = off
    end_max = len(data)

    # Phase 1 — prefix uncompressed f32 samples
    n_prefix = min(mask.prefix_count, num_samples)
    for _ in range(n_prefix):
        if p + 4 > end_max:
            return out, p - off
        out.append(struct.unpack_from("<f", data, p)[0])
        p += 4

    # Phase 2 — bit-packed samples
    n_packed = num_samples - n_prefix
    if n_packed > 0 and 0 < mask.bits_per_sample <= 32:
        factor = QUANT_SCALE[mask.bits_per_sample] * mask.scale
        bits = mask.bits_per_sample

        if bits == 8:
            for _ in range(n_packed):
                if p + 1 > end_max:
                    break
                v = data[p]
                p += 1
                out.append((v + 0.5) * factor + mask.base)
        elif bits == 16:
            for _ in range(n_packed):
                if p + 2 > end_max:
                    break
                v = struct.unpack_from("<H", data, p)[0]
                p += 2
                out.append((v + 0.5) * factor + mask.base)
        else:
            # General case: 16-bit shift register reload
            reg = 0
            nbits = 0
            mask_lo = (1 << bits) - 1
            for _ in range(n_packed):
                while nbits < bits:
                    if p + 2 > end_max:
                        return out, p - off
                    reg |= struct.unpack_from("<H", data, p)[0] << nbits
                    p += 2
                    nbits += 16
                v = reg & mask_lo
                reg >>= bits
                nbits -= bits
                out.append((v + 0.5) * factor + mask.base)

    # Phase 3 — delta decode (FUN_00dde310 prefix-sum)
    for i in range(1, len(out)):
        out[i] += out[i - 1]

    return out, p - off


def parse_track_masks(b: bytes, off: int, count: int) -> List[int]:
    """Read `count` u16 per-track encoding masks starting at `off`."""
    return [u16(b, off + i * 2) for i in range(count)]


def mask_static_counts(masks: List[int]) -> Tuple[int, int, int]:
    """Mirrors FUN_00dd6a30: counts source bits per channel group."""
    t = r = s = 0
    for m in masks:
        t += ((m >> 6) & 1) + ((m >> 7) & 1) + ((m >> 8) & 1)
        r += ((m >> 9) & 1) + ((m >> 10) & 1) + ((m >> 11) & 1) + ((m >> 12) & 1)
        s += ((m >> 13) & 1) + ((m >> 14) & 1) + ((m >> 15) & 1)
    return t, r, s


def mask_skip_flags(mask: int) -> Tuple[bool, bool, bool]:
    """Returns (zero_translation, identity_quat, unit_scale) flags."""
    return (mask & 0x3) == 2, (mask & 0xC) == 8, (mask & 0x30) == 0x20


# -----------------------------------------------------------------------------
# FUN_00dd7070 mirror: 14-int output struct describing the per-track
# split between skip / static / dynamic across both quat and float track arrays.
# -----------------------------------------------------------------------------
@dataclass
class MaskStats:
    # Dynamic counts (computed):
    dyn_trans_channels: int
    dyn_rot_channels: int
    dyn_scale_channels: int
    active_float_tracks: int
    # Skip counts (per-track skip-flag sums, channel-weighted):
    trans_skip_channels: int      # 3 per skip-flag
    rot_skip_channels: int        # 4 per skip-flag
    scale_skip_channels: int      # 3 per skip-flag
    # Static-source bit sums (across both arrays):
    trans_static_channels: int
    rot_static_channels: int
    scale_static_channels: int
    zero_mask_floats: int
    # Hints:
    rot_channel_budget: int       # = num_quat * 10
    num_float: int
    avg_bits_per_channel: int

    @property
    def total_static_channels(self) -> int:
        return (
            self.trans_static_channels
            + self.rot_static_channels
            + self.scale_static_channels
            + self.zero_mask_floats
        )

    @property
    def total_dynamic_channels(self) -> int:
        return (
            self.dyn_trans_channels
            + self.dyn_rot_channels
            + self.dyn_scale_channels
            + self.active_float_tracks
        )


def analyze_track_masks(
    quat_masks: List[int], float_masks: List[int]
) -> MaskStats:
    """Mirror of FUN_00dd7070. Splits the per-track mask analysis into
    skip / static-source / dynamic counts for the four channel groups
    (trans, rot, scale, scalar-float)."""
    num_quat = len(quat_masks)
    num_float = len(float_masks)

    # Skip-flag sums — only over quat-track masks (FUN_00dd7070 loop).
    trans_skip = 0
    rot_skip = 0
    scale_skip = 0
    for m in quat_masks:
        if (m & 0x3) == 2:
            trans_skip += 3
        if (m & 0xC) == 8:
            rot_skip += 4
        if (m & 0x30) == 0x20:
            scale_skip += 3

    # Source-bit sums — over both arrays (FUN_00dd6a30 + FUN_00dd6ad0).
    t_src, r_src, s_src = mask_static_counts(quat_masks)
    t2, r2, s2 = mask_static_counts(float_masks)
    trans_src = t_src + t2
    rot_src = r_src + r2
    scale_src = s_src + s2
    zero_floats = sum(1 for m in float_masks if m == 0)

    # Dynamic counts = total_channels - skip - static.
    dyn_t = num_quat * 3 - trans_skip - trans_src
    dyn_r = num_quat * 4 - rot_skip - rot_src
    dyn_s = num_quat * 3 - scale_skip - scale_src
    active_float = num_float - zero_floats

    total_static = trans_src + rot_src + scale_src + zero_floats
    avg_bits = ((10 * num_quat + num_float) // total_static) if total_static else 0

    return MaskStats(
        dyn_trans_channels=dyn_t,
        dyn_rot_channels=dyn_r,
        dyn_scale_channels=dyn_s,
        active_float_tracks=active_float,
        trans_skip_channels=trans_skip,
        rot_skip_channels=rot_skip,
        scale_skip_channels=scale_skip,
        trans_static_channels=trans_src,
        rot_static_channels=rot_src,
        scale_static_channels=scale_src,
        zero_mask_floats=zero_floats,
        rot_channel_budget=num_quat * 10,
        num_float=num_float,
        avg_bits_per_channel=avg_bits,
    )


# -----------------------------------------------------------------------------
# Skeleton
# -----------------------------------------------------------------------------
@dataclass
class Bone:
    index: int
    name: str
    parent: int  # 0xFFFF = root
    pos: Tuple[float, float, float]
    quat: Tuple[float, float, float, float]
    scale: Tuple[float, float, float]


@dataclass
class Skeleton:
    bone_count: int
    bones: List[Bone]
    rig_hash1: int
    rig_hash2: int


def parse_rig(rig_path: str, rig_header_path: Optional[str] = None) -> Skeleton:
    with open(rig_path, "rb") as f:
        rig = f.read()

    # 1. Bone names: NUL-terminated ASCII strings packed at the start.
    #    They run until we hit the name-table region (large gap of 00 padding
    #    typically followed by repeating 8-byte entries).
    names: List[str] = []
    pos = 0
    while pos < len(rig):
        end = rig.find(b"\x00", pos)
        if end < 0:
            break
        s = rig[pos:end]
        # break when we leave printable-ASCII territory or hit a 0-length string
        if not s or any(c < 0x20 or c >= 0x7F for c in s):
            break
        names.append(s.decode("ascii"))
        pos = end + 1

    n = len(names)

    # 2. Parents at 0x720 (u16 each). 0xFFFF = root.
    parents = [u16(rig, 0x720 + i * 2) for i in range(n)]

    # 3. Bind-pose local transforms at 0x980 (48 B per bone).
    bones: List[Bone] = []
    base = 0x980
    for i in range(n):
        off = base + i * 48
        if off + 48 > len(rig):
            break
        bones.append(
            Bone(
                index=i,
                name=names[i],
                parent=parents[i],
                pos=vec3(rig, off + 0),
                quat=qnorm(vec4(rig, off + 16)),
                scale=vec3(rig, off + 32),
            )
        )

    rig_hash1 = rig_hash2 = 0
    if rig_header_path and os.path.exists(rig_header_path):
        with open(rig_header_path, "rb") as f:
            hdr = f.read()
        if len(hdr) >= 0x10:
            rig_hash1 = u32(hdr, 0x04)
            rig_hash2 = u32(hdr, 0x08)

    return Skeleton(
        bone_count=len(bones),
        bones=bones,
        rig_hash1=rig_hash1,
        rig_hash2=rig_hash2,
    )


# -----------------------------------------------------------------------------
# AnimResource.header
# -----------------------------------------------------------------------------
@dataclass
class AnimHeader:
    version: int
    hash1: int
    hash2: int
    num_skel: int
    num_blocks: int
    animated_bones: List[int]   # bone indices animated by this clip
    duration_seconds: float
    blend_unknown: float
    events_raw: str
    events: List[str]
    rig_hash_match: bool = False  # filled in by caller


def parse_anim_header(
    path: str,
    max_bone_index: int = 0x5F,
    expected_duration: Optional[float] = None,
) -> AnimHeader:
    """Parse an .AnimResource.header sidecar.

    `max_bone_index` is the highest bone index we'll accept. Defaults to 0x5F
    (95), which fits b20_horse's 92-bone rig. Pass the rig bone count - 1
    when calling for other characters.

    `expected_duration` is the (frames_per_period - 1) / fps computed from
    the dnap header. We use it to disambiguate cases where a valid bone
    index byte happens to coincide with the leading byte of the duration
    float (e.g. relaxed_walk, where bone 0x55 is also the float's mantissa).
    """
    with open(path, "rb") as f:
        b = f.read()

    version = u32(b, 0x00)
    h1 = u32(b, 0x04)
    h2 = u32(b, 0x08)
    num_skel = u8(b, 0x0C)
    num_blocks = u8(b, 0x0F)

    # Animated bone indices: strictly-ascending bytes <= max_bone_index,
    # starting at 0x10. Optionally truncate when the next byte's float-window
    # decodes to a value close to the expected duration — that catches the
    # rare case where a valid bone index byte coincides with a duration-float
    # mantissa (e.g. relaxed_walk's 55 55 95 3F = 1.1667).
    bones: List[int] = []
    p = 0x10
    prev = -1
    while p < len(b) and b[p] <= max_bone_index and b[p] > prev:
        if expected_duration is not None and p + 4 <= len(b):
            candidate = f32(b, p)
            if 0.0 < candidate < 60.0 and abs(candidate - expected_duration) < 0.01:
                break  # this byte is the start of the duration float
        bones.append(b[p])
        prev = b[p]
        p += 1
    duration = 0.0
    blend = 0.0
    if p + 8 <= len(b):
        duration = f32(b, p)
        blend = f32(b, p + 4)

    # Event list: 'vena' marker, u32 size, ASCII text, 'mina' tail
    events_raw = ""
    events: List[str] = []
    vidx = b.find(b"vena")
    if vidx >= 0 and vidx + 8 <= len(b):
        size = u32(b, vidx + 4)
        text_end = min(vidx + 8 + size, len(b))
        events_raw = b[vidx + 8 : text_end].rstrip(b"\x00").decode(
            "ascii", "replace"
        )
        # The text is a single-line list:
        #   [AnimEventKey{...},AnimEventKey{...}]
        if events_raw.startswith("[") and events_raw.endswith("]"):
            inner = events_raw[1:-1]
            # split on ',AnimEventKey' keeping the prefix on the first one
            if inner:
                parts = inner.split(",AnimEventKey")
                events = [parts[0]] + ["AnimEventKey" + p for p in parts[1:]]
                events = [e.strip() for e in events if e.strip()]

    return AnimHeader(
        version=version,
        hash1=h1,
        hash2=h2,
        num_skel=num_skel,
        num_blocks=num_blocks,
        animated_bones=bones,
        duration_seconds=duration,
        blend_unknown=blend,
        events_raw=events_raw,
        events=events,
    )


# -----------------------------------------------------------------------------
# AnimResource (dnap) body
# -----------------------------------------------------------------------------
@dataclass
class AnimBlock:
    index: int
    rot_offset: int
    rot_size: int
    trans_offset: int
    trans_size: int
    rot_quats: List[Optional[Tuple[float, float, float, float]]]


@dataclass
class AnimResource:
    file_size: int
    magic: str
    period_seconds: float
    fps: float
    total_frames: int
    version: int
    frames_per_period: int
    num_tracks: int
    num_blocks: int
    raw_metadata: str          # 0x18..0x40 hex-dumped
    section_sizes: List[int]   # secs[0..7]
    payload_offset: int        # secs[2]
    # The runtime struct's data buffer starts at file offset 0x68. The first
    # 4 bytes are a header, then a u16 per-track encoding-mask array of length
    # (num_quat + num_float). The dnap header at +0x34/+0x36 gives the split.
    num_quat_tracks: int       # = file[+0x34], formerly "num_static_rot"
    num_float_tracks: int      # = file[+0x36], formerly "num_static_trans"
    track_masks: List[int]     # u16 per-track encoding masks
    quat_track_masks: List[int]
    float_track_masks: List[int]
    mask_stats: Optional["MaskStats"]
    reference_quat_section_offset: int
    reference_quat_section_size: int
    reference_quats: List[Optional[Tuple[float, float, float, float]]]
    blocks: List[AnimBlock]
    # Backward-compat aliases (kept for downstream tooling that still reads
    # the old field names):
    num_static_rot: int
    num_static_trans: int


def parse_anim_resource(
    path: str, num_blocks_override: Optional[int] = None
) -> AnimResource:
    with open(path, "rb") as f:
        d = f.read()
    if d[:4] != b"dnap":
        raise ValueError(f"{path}: bad magic {d[:4]!r}")

    period_s = f32(d, 0x04)
    fps = f32(d, 0x08)
    total_frames = u16(d, 0x0C)
    version = u16(d, 0x0E)
    frames_per_period = u16(d, 0x10)
    num_tracks = u16(d, 0x12)
    # 0x16 is num "sized" blocks (those with explicit secs entries). The last
    # block can be implicit (consumes the file tail) so the .header byte at
    # 0x0F is the authoritative total. We default to dnap and let the caller
    # override using the .header value.
    num_blocks = u16(d, 0x16)
    # Static counts in the metadata block (validated empirically):
    #   0x34 u16 = num_static_rot   (tracks whose rotation comes from a
    #                                static slot and not a per-frame stream)
    #   0x36 u16 = num_static_trans (same for translation)
    # For relaxed_trot: (2, 34) — sums to num_tracks(36) ✓.
    # For relaxed_breathe: (2, 18) — sums to 20 (one less than num_tracks).
    num_static_rot = u16(d, 0x34)
    num_static_trans = u16(d, 0x36)

    raw_meta = d[0x18:0x40].hex()
    secs = [u32(d, 0x40 + i * 4) for i in range(8)]
    payload_off = secs[2]

    # The runtime "data buffer" (this+0x68 in the runtime struct) holds the
    # actual encoded animation. FUN_00dcc280 byte-swaps a u16 array at
    # `data + 4` of length (num_quat + num_float), and FUN_00dd6a30 /
    # FUN_00dd7b00 read those u16s as per-track encoding masks (skip flags
    # + per-channel static/dynamic source bits).
    #
    # NOTE: The exact dnap-file offset where the runtime "data buffer" lives
    # is still uncertain. If we naïvely treat file offset 0x68 as the buffer
    # start, the u16s at 0x6C come out as sequential values (0x01, 0x02, …)
    # which look like a remap/index table rather than encoding masks. So the
    # data buffer is presumably copied from a different file region by the
    # loader (the exact mapping requires the file-package loader's
    # vftable[0xd] which we still haven't disassembled).
    #
    # We expose the candidate u16 array at 0x6C verbatim under
    # `track_masks_or_remap` plus the analyzed MaskStats so downstream code
    # can experiment.
    num_quat_tracks = num_static_rot
    num_float_tracks = num_static_trans
    candidate_off = 0x6C
    total_masks = num_quat_tracks + num_float_tracks
    track_masks = [u16(d, candidate_off + i * 2) for i in range(total_masks)]
    quat_masks = track_masks[:num_quat_tracks]
    float_masks = track_masks[num_quat_tracks:]
    mstats: Optional[MaskStats] = None
    if track_masks:
        mstats = analyze_track_masks(quat_masks, float_masks)

    # Reference-pose quats. Section size = secs[1], 6 bytes each.
    # The slot count usually equals num_tracks rounded to whatever; some slots
    # are sentinels (no rotation override).
    ref_size = secs[1]
    ref_off = payload_off
    ref_quats: List[Optional[Tuple[float, float, float, float]]] = []
    n_ref = ref_size // 6
    for i in range(n_ref):
        ref_quats.append(decode_smallest3_48(d[ref_off + i * 6 : ref_off + i * 6 + 6]))

    # Per-block sections: sizes are alternating rot/trans starting at secs[3].
    # If the caller knows the true block count from the .header (often one
    # higher than the dnap value), we honor that and let the trailing block
    # consume whatever is left.
    blocks: List[AnimBlock] = []
    cursor = ref_off + ref_size
    block_count = num_blocks_override if num_blocks_override is not None else num_blocks
    for bi in range(block_count):
        ri = 3 + bi * 2
        ti = 4 + bi * 2
        rs = secs[ri] if ri < len(secs) else 0
        ts = secs[ti] if ti < len(secs) else 0
        # Last block: if both are 0 (or only rot is 0), it consumes the rest.
        if rs == 0 and ts == 0:
            rs = max(0, len(d) - cursor)
        rot_off = cursor
        trans_off = cursor + rs
        # Decode any embedded smallest3-48 quats from the rotation chunk
        # (these are mixed with bitstream control bytes; we just collect any
        # 6-byte windows that decode to a valid unit quaternion).
        rot_quats: List[Optional[Tuple[float, float, float, float]]] = []
        for k in range(rs // 6):
            window = d[rot_off + k * 6 : rot_off + k * 6 + 6]
            q = decode_smallest3_48(window)
            if q is None:
                rot_quats.append(None)
                continue
            mag = math.sqrt(sum(x * x for x in q))
            if 0.97 < mag < 1.03:
                rot_quats.append(q)
            else:
                rot_quats.append(None)

        blocks.append(
            AnimBlock(
                index=bi,
                rot_offset=rot_off,
                rot_size=rs,
                trans_offset=trans_off,
                trans_size=ts,
                rot_quats=rot_quats,
            )
        )
        cursor += rs + ts

    return AnimResource(
        file_size=len(d),
        magic="dnap",
        period_seconds=period_s,
        fps=fps,
        total_frames=total_frames,
        version=version,
        frames_per_period=frames_per_period,
        num_tracks=num_tracks,
        num_blocks=num_blocks,
        raw_metadata=raw_meta,
        section_sizes=secs,
        payload_offset=payload_off,
        num_quat_tracks=num_quat_tracks,
        num_float_tracks=num_float_tracks,
        track_masks=track_masks,
        quat_track_masks=quat_masks,
        float_track_masks=float_masks,
        mask_stats=mstats,
        reference_quat_section_offset=ref_off,
        reference_quat_section_size=ref_size,
        reference_quats=ref_quats,
        blocks=blocks,
        num_static_rot=num_static_rot,
        num_static_trans=num_static_trans,
    )


# -----------------------------------------------------------------------------
# Stance / ComboPose / ComboAnim
# -----------------------------------------------------------------------------
@dataclass
class PropertyDoc:
    file_type: str        # "Stance", "ComboPose", "ComboAnim"
    file_size: int
    declared_size: int    # u32 at offset 0
    version: int          # u8 at offset 4
    root_type: str
    properties: Dict[str, Any]
    referenced_assets: List[str]  # @path references
    raw_text: str


def _parse_dfprop(text: str) -> Tuple[str, Any]:
    """Parse a value starting at 0 of `text`. Returns (value, remaining_text).
    DoubleFine property syntax (very loose):
      Type{Key=Value;Key=Value;}
      [v,v,v]                     list
      <v,v,v>                     vector
      @ref/path                   asset reference
      bare token / number / 0/1   scalar
    """
    text = text.lstrip()
    if not text:
        return "", ""

    c = text[0]
    if c == "{":
        # already-typeless object (rare)
        return _parse_object("Object", text)
    if c == "[":
        return _parse_list(text)
    if c == "<":
        return _parse_vector(text)
    if c == "@":
        # @path: read until `;` `,` `]` `}` or end
        end = len(text)
        for term in (";", ",", "]", "}"):
            j = text.find(term)
            if 0 <= j < end:
                end = j
        return text[:end], text[end:]
    # Could be either a typed object `Foo{...}` or a scalar token.
    # Read an identifier; if next char is `{`, parse object; else scalar.
    j = 0
    while j < len(text) and (text[j].isalnum() or text[j] in "_:."):
        j += 1
    ident = text[:j]
    rest = text[j:]
    if rest.startswith("{"):
        return _parse_object(ident, rest)
    # scalar: include any trailing characters until terminator
    end = len(rest)
    for term in (";", ",", "]", "}"):
        k = rest.find(term)
        if 0 <= k < end:
            end = k
    return ident + rest[:end], rest[end:]


def _parse_object(typename: str, text: str) -> Tuple[Dict[str, Any], str]:
    assert text.startswith("{")
    text = text[1:]
    obj: Dict[str, Any] = {"__type__": typename}
    while text and not text.startswith("}"):
        eq = text.find("=")
        if eq < 0:
            break
        key = text[:eq].strip()
        text = text[eq + 1 :]
        value, text = _parse_dfprop(text)
        obj[key] = value
        text = text.lstrip()
        if text.startswith(";"):
            text = text[1:]
        text = text.lstrip()
    if text.startswith("}"):
        text = text[1:]
    return obj, text


def _parse_list(text: str) -> Tuple[List[Any], str]:
    assert text.startswith("[")
    text = text[1:]
    out: List[Any] = []
    while text and not text.startswith("]"):
        v, text = _parse_dfprop(text)
        out.append(v)
        text = text.lstrip()
        if text.startswith(","):
            text = text[1:]
        text = text.lstrip()
    if text.startswith("]"):
        text = text[1:]
    return out, text


def _parse_vector(text: str) -> Tuple[List[float], str]:
    assert text.startswith("<")
    end = text.find(">")
    if end < 0:
        return [], text[1:]
    parts = text[1:end].split(",")
    out: List[float] = []
    for p in parts:
        try:
            out.append(float(p))
        except ValueError:
            pass
    return out, text[end + 1 :]


def parse_prop_doc(path: str, file_type: str) -> PropertyDoc:
    with open(path, "rb") as f:
        b = f.read()
    declared = u32(b, 0x00)
    version = u8(b, 0x04)
    text = b[0x05:].rstrip(b"\x00").decode("ascii", "replace")
    obj, _ = _parse_dfprop(text)
    if not isinstance(obj, dict):
        obj = {"__value__": obj}
    refs = sorted(set(_collect_asset_refs(text)))
    root = obj.get("__type__", file_type) if isinstance(obj, dict) else file_type
    return PropertyDoc(
        file_type=file_type,
        file_size=len(b),
        declared_size=declared,
        version=version,
        root_type=root,
        properties=obj,
        referenced_assets=refs,
        raw_text=text,
    )


def _collect_asset_refs(text: str) -> List[str]:
    out: List[str] = []
    i = 0
    while i < len(text):
        if text[i] == "@":
            j = i + 1
            while j < len(text) and text[j] not in ";,]}>":
                j += 1
            ref = text[i + 1 : j]
            if ref:
                out.append(ref)
            i = j
        else:
            i += 1
    return out


# -----------------------------------------------------------------------------
# Mesh / PhysicsRigidBody (minimal)
# -----------------------------------------------------------------------------
def parse_mesh_header(path: str) -> Dict[str, Any]:
    with open(path, "rb") as f:
        b = f.read()
    return {
        "file_size": len(b),
        "first_32_hex": b[:32].hex(),
        # Mesh.Header is a small index/footprint; full parsing is beyond
        # the animation focus of this script.
    }


def parse_physics_rigid_body(path: str) -> Dict[str, Any]:
    with open(path, "rb") as f:
        b = f.read()
    return {
        "file_size": len(b),
        "first_32_hex": b[:32].hex(),
    }


# -----------------------------------------------------------------------------
# JSON helpers
# -----------------------------------------------------------------------------
def to_jsonable(obj: Any) -> Any:
    if hasattr(obj, "__dataclass_fields__"):
        return {k: to_jsonable(v) for k, v in asdict(obj).items()}
    if isinstance(obj, (list, tuple)):
        return [to_jsonable(v) for v in obj]
    if isinstance(obj, dict):
        return {k: to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, float):
        return round(obj, 6)
    return obj


def write_json(path: str, payload: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(to_jsonable(payload), f, indent=2)


# -----------------------------------------------------------------------------
# Driver
# -----------------------------------------------------------------------------
def parse_b20_horse(b20_dir: str, out_dir: str) -> Dict[str, Any]:
    summary: Dict[str, Any] = {"character": os.path.basename(b20_dir.rstrip("\\/"))}

    # --- Skeleton -----------------------------------------------------------
    rig_dir = os.path.join(b20_dir, "rig")
    rig_path = os.path.join(rig_dir, "b20_horse.Rig")
    rig_hdr = os.path.join(rig_dir, "b20_horse.Rig.Header")
    if os.path.exists(rig_path):
        skel = parse_rig(rig_path, rig_hdr if os.path.exists(rig_hdr) else None)
        write_json(os.path.join(out_dir, "skeleton.json"), skel)
        summary["skeleton"] = {
            "bone_count": skel.bone_count,
            "rig_hash1": f"0x{skel.rig_hash1:08X}",
            "rig_hash2": f"0x{skel.rig_hash2:08X}",
            "first_bones": [b.name for b in skel.bones[:10]],
        }
    else:
        skel = None

    # --- Stances ------------------------------------------------------------
    stance_summary = []
    for fname in sorted(os.listdir(b20_dir)):
        if fname.endswith(".Stance"):
            doc = parse_prop_doc(os.path.join(b20_dir, fname), "Stance")
            write_json(
                os.path.join(out_dir, "stances", fname + ".json"),
                doc,
            )
            stance_summary.append(
                {
                    "name": fname,
                    "size": doc.file_size,
                    "version": doc.version,
                    "root_type": doc.root_type,
                    "asset_refs": len(doc.referenced_assets),
                }
            )
    summary["stances"] = stance_summary

    # --- ComboPoses (top-level) --------------------------------------------
    combopose_summary = []
    for fname in sorted(os.listdir(b20_dir)):
        if fname.endswith(".ComboPose"):
            doc = parse_prop_doc(os.path.join(b20_dir, fname), "ComboPose")
            write_json(
                os.path.join(out_dir, "combo_poses", fname + ".json"),
                doc,
            )
            combopose_summary.append(
                {
                    "name": fname,
                    "size": doc.file_size,
                    "asset_refs": len(doc.referenced_assets),
                }
            )
    summary["combo_poses"] = combopose_summary

    # --- Animations ---------------------------------------------------------
    anim_dir = os.path.join(b20_dir, "animations")
    anims_summary = []
    if os.path.isdir(anim_dir):
        for fname in sorted(os.listdir(anim_dir)):
            full = os.path.join(anim_dir, fname)
            if fname.endswith(".AnimResource"):
                base = fname[: -len(".AnimResource")]
                hdr_path = os.path.join(anim_dir, base + ".AnimResource.header")
                hdr: Optional[AnimHeader] = None
                if os.path.exists(hdr_path):
                    cap = (skel.bone_count - 1) if skel else 0x5F
                    # Peek the dnap header for an expected duration hint.
                    with open(full, "rb") as f:
                        dnap_head = f.read(0x18)
                    fps_hint = f32(dnap_head, 0x08)
                    fpp_hint = u16(dnap_head, 0x10)
                    expected_dur = (
                        (fpp_hint - 1) / fps_hint if fps_hint > 0 and fpp_hint > 0
                        else None
                    )
                    hdr = parse_anim_header(
                        hdr_path, max_bone_index=cap, expected_duration=expected_dur
                    )
                    if skel is not None:
                        with open(rig_hdr, "rb") as f:
                            rh = f.read()
                        rig_h1 = u32(rh, 0x04) if len(rh) >= 0x10 else 0
                        rig_h2 = u32(rh, 0x08) if len(rh) >= 0x10 else 0
                        hdr.rig_hash_match = (
                            hdr.hash1 == rig_h1 and hdr.hash2 == rig_h2
                        )
                # Use the .header's num_blocks (authoritative) when present.
                anim = parse_anim_resource(
                    full,
                    num_blocks_override=(hdr.num_blocks if hdr else None),
                )

                payload = {
                    "name": base,
                    "anim_resource": anim,
                    "anim_header": hdr,
                }
                # cross-reference: animated_bones -> bone names
                if skel is not None and hdr is not None:
                    payload["animated_bone_names"] = [
                        skel.bones[i].name if i < skel.bone_count else f"<bone_{i}>"
                        for i in hdr.animated_bones
                    ]
                    # Per-track encoding masks decoded into channel-by-channel
                    # source descriptions, paired with the animated bone the
                    # quat-track applies to.
                    track_descriptions = []
                    for ti, m in enumerate(anim.quat_track_masks):
                        skip_t, skip_r, skip_s = mask_skip_flags(m)
                        bone_idx = (
                            hdr.animated_bones[ti]
                            if ti < len(hdr.animated_bones)
                            else None
                        )
                        bone_name = (
                            skel.bones[bone_idx].name
                            if bone_idx is not None and bone_idx < skel.bone_count
                            else f"<bone_{bone_idx}>"
                        )
                        track_descriptions.append(
                            {
                                "track": ti,
                                "type": "quat",
                                "mask_hex": f"0x{m:04X}",
                                "bone_index": bone_idx,
                                "bone_name": bone_name,
                                "translation": (
                                    "skip"
                                    if skip_t
                                    else [
                                        "static" if (m >> 8) & 1 else "dynamic",
                                        "static" if (m >> 7) & 1 else "dynamic",
                                        "static" if (m >> 6) & 1 else "dynamic",
                                    ]
                                ),
                                "rotation": (
                                    "identity"
                                    if skip_r
                                    else [
                                        "static" if (m >> 12) & 1 else "dynamic",
                                        "static" if (m >> 11) & 1 else "dynamic",
                                        "static" if (m >> 10) & 1 else "dynamic",
                                        "static" if (m >> 9) & 1 else "dynamic",
                                    ]
                                ),
                                "scale": (
                                    "unit"
                                    if skip_s
                                    else [
                                        "static" if (m >> 15) & 1 else "dynamic",
                                        "static" if (m >> 14) & 1 else "dynamic",
                                        "static" if (m >> 13) & 1 else "dynamic",
                                    ]
                                ),
                            }
                        )
                    for ti, m in enumerate(anim.float_track_masks):
                        track_descriptions.append(
                            {
                                "track": anim.num_quat_tracks + ti,
                                "type": "float",
                                "mask_hex": f"0x{m:04X}",
                                "is_default": m == 0,
                            }
                        )
                    payload["track_descriptions"] = track_descriptions
                write_json(os.path.join(out_dir, "animations", base + ".json"), payload)

                # Compact summary entry
                ref_kept = sum(1 for q in anim.reference_quats if q is not None)
                rot_kept = [
                    sum(1 for q in bl.rot_quats if q is not None)
                    for bl in anim.blocks
                ]
                anims_summary.append(
                    {
                        "name": base,
                        "size": anim.file_size,
                        "fps": round(anim.fps, 3),
                        "period_s": round(anim.period_seconds, 4),
                        "frames_per_period": anim.frames_per_period,
                        "total_frames": anim.total_frames,
                        "version": anim.version,
                        "num_tracks": anim.num_tracks,
                        "num_blocks_dnap": anim.num_blocks,
                        "num_blocks": len(anim.blocks),  # authoritative
                        "ref_quats_total": len(anim.reference_quats),
                        "ref_quats_decoded": ref_kept,
                        "rot_quats_decoded_per_block": rot_kept,
                        "events": len(hdr.events) if hdr else 0,
                        "duration_s": round(hdr.duration_seconds, 4) if hdr else None,
                        "rig_hash_match": hdr.rig_hash_match if hdr else None,
                        "animated_bone_count": (
                            len(hdr.animated_bones) if hdr else None
                        ),
                    }
                )
            elif fname.endswith(".ComboAnim"):
                doc = parse_prop_doc(full, "ComboAnim")
                write_json(
                    os.path.join(out_dir, "combo_anims", fname + ".json"),
                    doc,
                )
                anims_summary.append(
                    {
                        "name": fname,
                        "size": doc.file_size,
                        "type": "ComboAnim",
                        "asset_refs": len(doc.referenced_assets),
                    }
                )
    summary["animations"] = anims_summary

    # --- Mesh / PhysicsRigidBody (lightweight) -----------------------------
    mesh_summary = []
    if os.path.exists(rig_dir):
        for fname in sorted(os.listdir(rig_dir)):
            if fname.endswith(".Mesh"):
                mesh_summary.append(
                    {
                        "name": fname,
                        **parse_mesh_header(os.path.join(rig_dir, fname)),
                    }
                )
    summary["meshes"] = mesh_summary

    model_dir = os.path.join(b20_dir, "model")
    physics_summary = []
    if os.path.isdir(model_dir):
        for fname in sorted(os.listdir(model_dir)):
            if fname.endswith(".PhysicsRigidBody"):
                physics_summary.append(
                    {
                        "name": fname,
                        **parse_physics_rigid_body(os.path.join(model_dir, fname)),
                    }
                )
    summary["physics_rigid_bodies"] = physics_summary

    write_json(os.path.join(out_dir, "summary.json"), summary)
    return summary


def main() -> int:
    b20 = sys.argv[1] if len(sys.argv) > 1 else B20_DIR
    out = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_OUT
    if not os.path.isdir(b20):
        print(f"ERROR: not a directory: {b20}")
        return 1
    summary = parse_b20_horse(b20, out)

    # Print compact terminal summary
    print(f"\nParsed {summary['character']} -> {out}\n")
    sk = summary.get("skeleton")
    if sk:
        print(
            f"  Skeleton: {sk['bone_count']} bones  hashes "
            f"{sk['rig_hash1']} / {sk['rig_hash2']}"
        )
    print(f"  Stances:        {len(summary.get('stances', []))}")
    print(f"  ComboPoses:     {len(summary.get('combo_poses', []))}")
    print(f"  Meshes:         {len(summary.get('meshes', []))}")
    print(f"  Physics bodies: {len(summary.get('physics_rigid_bodies', []))}")
    print(f"  Animations:     {len(summary.get('animations', []))}")
    print()
    print(
        f"  {'name':<30} {'fps':>6} {'period_s':>9} {'dur_s':>7} "
        f"{'frames':>7} {'tracks':>7} {'blocks':>7} {'events':>7} {'hashOK':>7}"
    )
    for a in summary.get("animations", []):
        if "fps" not in a:
            continue
        print(
            f"  {a['name']:<30} {a['fps']:>6.2f} {a['period_s']:>9.4f} "
            f"{(a.get('duration_s') or 0):>7.4f} "
            f"{a['total_frames']:>7d} {a['num_tracks']:>7d} "
            f"{a['num_blocks']:>7d} {a['events']:>7d} "
            f"{'yes' if a.get('rig_hash_match') else 'no':>7}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
