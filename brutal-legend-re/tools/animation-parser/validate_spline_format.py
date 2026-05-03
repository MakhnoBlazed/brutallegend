#!/usr/bin/env python3
"""
validate_spline_format.py

Empirically test whether dnap data layout matches the
hkaSplineCompressedAnimation interpretation derived from
FUN_00dd1a00 + DAT_00e71108/120.

We try to:
1. Read all 27 b20_horse dnap files
2. For each, check whether reading 4-byte quat track headers
   (per FUN_00dd1a00) gives plausible encoding selectors
3. Validate the rotation encoding choices fall in 0..5 range
4. Count which encodings are actually used

If the format is correct, we'll see encoding values 0..5 with
a reasonable distribution. If wrong, we'll see garbage values.
"""

from __future__ import annotations

import os
import struct
import sys
from collections import Counter
from typing import List

ANIM_DIR = (
    r"D:\SteamLibrary\steamapps\common\BrutalLegend\DoubleFineModTool"
    r"\unpacked\characters\quadrupeds\b20_horse\animations"
)


def parse_dnap_basics(path: str):
    with open(path, "rb") as f:
        d = f.read()
    if d[:4] != b"dnap":
        return None
    return {
        "data": d,
        "name": os.path.basename(path).replace(".AnimResource", ""),
        "file_size": len(d),
        "fps": struct.unpack_from("<f", d, 0x08)[0],
        "total_frames": struct.unpack_from("<H", d, 0x0C)[0],
        "frames_per_period": struct.unpack_from("<H", d, 0x10)[0],
        "num_tracks": struct.unpack_from("<H", d, 0x12)[0],
        "num_blocks_dnap": struct.unpack_from("<H", d, 0x16)[0],
        "num_quat": struct.unpack_from("<H", d, 0x34)[0],
        "num_float": struct.unpack_from("<H", d, 0x36)[0],
        "secs": [struct.unpack_from("<I", d, 0x40 + i * 4)[0] for i in range(8)],
    }


def try_parse_track_headers(d: bytes, off: int, num_quat: int, num_float: int):
    """Try to read num_quat × 4-byte quat headers + num_float × 1-byte float headers
    starting at `off`. Return decoded structure plus a 'plausibility score'."""
    quat_headers = []
    rot_encodings = []
    for i in range(num_quat):
        p = off + i * 4
        if p + 4 > len(d):
            return None, 0
        flags = d[p]
        rot_enc = (flags >> 2) & 0x0F
        quat_headers.append({
            "addr": p,
            "flags_hex": f"0x{flags:02X}",
            "trans_enc": flags & 3,
            "rot_enc": rot_enc,
            "scale_enc": flags >> 6,
            "trans_sub": d[p + 1],
            "rot_sub": d[p + 2],
            "scale_sub": d[p + 3],
        })
        rot_encodings.append(rot_enc)

    float_off = off + num_quat * 4
    float_headers = []
    for i in range(num_float):
        p = float_off + i
        if p >= len(d):
            return None, 0
        b = d[p]
        float_headers.append({
            "addr": p,
            "raw_hex": f"0x{b:02X}",
            "encoding": (b >> 1) & 3,
        })

    # Plausibility score: rot encodings in 0..5 are valid
    valid_rot = sum(1 for e in rot_encodings if 0 <= e <= 5)
    score = valid_rot / max(1, len(rot_encodings))
    return {"quat_headers": quat_headers, "float_headers": float_headers}, score


def main():
    print(f"{'name':<30} {'file':>5} {'numQ':>4} {'numF':>4} "
          f"{'best_off':>10} {'score':>6} {'rot_encs':<24}")
    print("-" * 100)

    candidate_offsets = [
        ("0x60", 0x60),
        ("0x64", 0x64),
        ("0x68", 0x68),
        ("0x6C", 0x6C),
        ("secs[2]", None),  # filled per file
        ("after 0x68 + secs[1]", None),  # try after static section
    ]

    overall_rot_counter = Counter()

    for fname in sorted(os.listdir(ANIM_DIR)):
        if not fname.endswith(".AnimResource"):
            continue
        info = parse_dnap_basics(os.path.join(ANIM_DIR, fname))
        if info is None:
            continue

        # Try several candidate offsets, pick the one with the best
        # plausibility score
        best_score = -1.0
        best_off_name = None
        best_result = None

        for off_name, off in candidate_offsets:
            if off is None:
                if off_name == "secs[2]":
                    off = info["secs"][2]
                elif off_name == "after 0x68 + secs[1]":
                    off = 0x68 + info["secs"][1]
            if off >= info["file_size"]:
                continue
            res, score = try_parse_track_headers(
                info["data"], off, info["num_quat"], info["num_float"])
            if res and score > best_score:
                best_score = score
                best_off_name = off_name
                best_result = res

        rot_encs = []
        if best_result:
            rot_encs = [h["rot_enc"] for h in best_result["quat_headers"]]
            for e in rot_encs:
                overall_rot_counter[e] += 1

        rot_summary = ",".join(str(e) for e in rot_encs[:8])
        print(f"{info['name']:<30} {info['file_size']:>5} {info['num_quat']:>4} "
              f"{info['num_float']:>4} {best_off_name or '?':>10} "
              f"{best_score:>6.2%} {rot_summary:<24}")

    print()
    print("=== Aggregate rotation-encoding histogram across all animations ===")
    for enc, count in sorted(overall_rot_counter.items()):
        marker = " [VALID]" if 0 <= enc <= 5 else " [INVALID - out of range]"
        print(f"  encoding {enc:>2}: {count:>4} occurrences{marker}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
