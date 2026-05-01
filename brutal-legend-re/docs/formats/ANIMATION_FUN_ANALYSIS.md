# Brutal Legend animation FUN_ analysis

Cross-reference of every `FUN_*.txt` at the top level of `ghidra_export/`,
synthesized across multiple export passes. The on-disk `dnap` format
is `hkaDeltaCompressedAnimation` (Havok Delta-Compressed Animation)
wrapped in a custom 8-section header with smallest3-48 reference quats.

---

## 1. Summary by role

### Decompression core — on-disk → quaternion path

| FUN | Role |
|---|---|
| `FUN_00a66470` (×2 aliases) | **zlib `inflate()`** verbatim. Used by `Rs_Decompressor` for *file-level* gzip blobs. NOT the dnap track decoder. |
| `FUN_00a69d00` | **zlib `inflate_table()`** — Huffman canonical-code builder. |
| **`FUN_00dcca00`** | **`hkaDeltaCompressedAnimation` dtor** ⭐ NEW. Frees `this+0x68` (data buffer, size at `this+0x6c`). |
| `FUN_00dcca40` | `StDecompressD` — sample one frame from a Delta animation. Reads `this+0x10/0x14/0x24/0x28/0x2c/0x30/0x34/0x38/0x3c/0x48/0x50/0x58/0x5c`. |
| `FUN_00dccfb0` | `StDecompressDChunk` outer wrapper — does (frame, frame+1) lerp via `FUN_00dcbdb0`. |
| `FUN_00dcbdb0` | Time → (frame_index, lerp_t). `fVar1 = (frames-1) * (time / this[0xc])`. Confirms `this+0xc = duration_seconds`. |
| `FUN_00dcc100` | Per-track delta scratch fill. Calls `00dde3c0` + `00dde310` + `00dddf80`. |
| `FUN_00dd1d10` | `hkaSplineCompressedAnimation::ctor` body. **Dead code** — Spline ctor is in the binary but never reached at runtime (the engine uses Delta, not Spline). |
| `FUN_00dd2a30` | Spline outer ctor. Same — dead code. |
| `FUN_00dd51b0` | `StDecompressWChunk` — wavelet variant. |
| `FUN_00dd5030` | Per-track wavelet scratch fill. |
| `FUN_00dd6ad0` | Bitstream front-end dispatcher (calls `00dd6a30`). |
| `FUN_00dd6a30` | Walks per-track u16 mask array, counts source bits per channel group. |
| `FUN_00dd7b00` | Per-track recompose. Reads 16-bit mask per track, writes (Tx,Ty,Tz,_, Qx,Qy,Qz,Qw, Sx,Sy,Sz,_) outputs. W=±2.0 sentinel triggers smallest3 reconstruction. |
| `FUN_00dde310` | Prefix-sum (delta-decode) — `[base, d1, d2, ...]` → cumulative. |
| `FUN_00dde3c0` | **The bit-packed sample dequantizer.** 8-bit / 16-bit / general-N-bit paths. Output = `(sample + 0.5) * scale / 2^N + base`. |
| `FUN_00dddf80` | Stream byte-size formula: `prefix*4 + ceil((n-prefix)*bits/8)`. |
| `FUN_00de6470` | Wavelet sparse-bitmap encoder. |
| `FUN_00de5910` | Inverse wavelet transform (CDF biorthogonal filter bank). |

### Resource-manager / lookup gateway

| FUN | Role |
|---|---|
| **`FUN_00451000`** | `RsMgr::acquire()` ⭐ — global resource lookup-with-load. On cache miss: dispatches to per-file-package loader's `vftable[0xc]` (read bytes) + `vftable[0xd]` (parse to typed resource). The dnap parser is inside `vftable[0xd]`. |

### Per-track / blending runtime

| FUN | Role |
|---|---|
| `FUN_00433130` | 4-quaternion SIMD-style normalize. |
| `FUN_00433d80` | Multi-track quaternion SLERP blend. |
| `FUN_00436c70` | 3×4 bone transform multiply + weight. |
| `FUN_0043bba0` | Visitor over an animation collection (calls vtable slots `0x9c`, `0xa0`, `0xa4`, `0xac`, `0xc`). |
| `FUN_0065ad10` | Animation track sampling driver. |
| `FUN_0065b260` | Stance-aware track sampling. |
| `FUN_0065ba90` | Per-track applicator — writes to skeleton, fires facial / foot-IK paths. |

### CoSkeleton lifecycle

| FUN | Role |
|---|---|
| `FUN_00a89a00` | `CoSkeleton::operator new` wrapper (0xA0 bytes). |
| `FUN_00a89af0` | `CoSkeleton::ctor` body — sets vftable, registers in global counter. |
| `FUN_00a89bf0` | `CoSkeleton::dtor`. |
| `FUN_00a89f50` | `CoSkeleton::lazyInit` — allocates 0x290-byte runtime state at `[0x24]`. |
| `FUN_00a8a4b0/4f0/530/580` | State-machine setters/clearers + onParentChange. |
| `FUN_00a8b230` | `TaskInstance<...>` ctor for thread tasks. |
| `FUN_00a8b770` | Thread-task body — backwards bone-list walk. |
| `FUN_00a89700` | One-time registry of `kAP_*` priority enum (26 entries). |
| `FUN_00a89a50` | `CoSkeleton` RTTI/class registration. |

### Resource consumers (look up already-loaded AnimResource)

All of these call `FUN_00451000(DAT_01009c80, hash, 0xf79460="AnimResource", 1000, ...)` to get a runtime AnimResource pointer. None of them parse dnap bytes.

| FUN | Role |
|---|---|
| `FUN_008f6f10` | `PlayAnimAction::computeMinMaxTime` — integrates duration over time-segments. |
| `FUN_008488f0` | PlayAnim-related, 2 lookup callsites. |
| `FUN_00764c40` | One-arg getter that triggers a lazy lookup. |
| `FUN_00a9a980/9e0/aa90/aae0/be30` | Animation property queries / state checks. |

### Schema / RTTI / attribute registration (init-time only)

These all run at process start to populate the engine's reflection database. Don't touch animation bytes.

| FUN | Class registered |
|---|---|
| `FUN_0040ea40` | `AnimCompressionParams` |
| `FUN_00541e10` | `AnimEvent_Footstep` |
| `FUN_009e1b40` | `CoRatMount::Idle` |
| `FUN_005fbac0` | `CcActorPlayAnim` command attributes |
| `FUN_00916350` | Master Stance schema (StartAnim, EndAnim, BreatheAnim, locomotion, combat, getup, stunned, etc.) |
| `FUN_00906c30` | Locomotion params (MinSpeed, blend times, GroundSpeeds). |
| `FUN_0090b860` | Head/eye/idle (EyeBlinkJoints, HeadJoint, idle ranges). |
| `FUN_0094ac90` | Idle anim state (IdleAnimation, ActiveAnimations, SleepRange). |
| `FUN_0095cb10` | Mount/attachment (CharacterStance, AttachJoint, etc.). |
| `FUN_00644490` | Dialogue line (BodyAnim, BodyAnimJoint, FaceAnimPriority). |
| `FUN_004ba320/aaa0` | Component vftable cache + teardown. |
| `FUN_00a11f30` | Wheel/suspension physics constraints. |
| `FUN_00a92360` | Leg-IK (HipJoint, KneeJoint, AnkleJoint, ToeJoint). |
| `FUN_00a38440` | Unit-order state machine (Attack, Defend, Follow). |

### Attribute-format text readers (used for `.Stance` / `.ComboPose` / etc.)

| FUN | Role |
|---|---|
| `FUN_009186b0`, `FUN_009186b8` | Vmethod wrappers. |
| `FUN_00918900` | Enum-attribute reader (`"invalid enum value"`). |
| `FUN_00918c30` | List-attribute reader (`"expected token '['"`). |
| `FUN_00918d60` | Reference-attribute reader. |
| `FUN_00919710` | Array-iterator helper. |

### Glue / boot / outliers

| FUN | Role |
|---|---|
| `FUN_0048a4b0` | Top-level boot sequencer. |
| `FUN_006b40a0` | Generic RTTI helper — pushes typed `Any` records. |
| `FUN_00e1baa0` | RTTI registration for `hkaFootstepAnalysisInfoContainer`. |

---

## 2. The bit-packed stream format (fully decoded)

Per-track encoded floats live in streams that look like:

```
struct StreamHeader {     // 12 bytes
    u8   bits_per_sample;
    u8   prefix_count;    // first N samples are uncompressed f32
    u16  pad;
    f32  scale;
    f32  base;
};
// followed by:
//   prefix_count × f32           uncompressed prefix samples
//   ceil((N - prefix) * bits / 8) bytes of bit-packed integers
```

**Decode:**
1. Read prefix uncompressed f32 samples verbatim.
2. Read remaining N-prefix samples bit-by-bit (16-bit shift-register reload).
3. Dequantize each as `(sample + 0.5) * scale / 2^bits + base`.
4. **Prefix-sum the entire array** (delta-decode): `out[i] += out[i-1]`.

This is mirrored in `decode_bit_packed_stream()` in `b20_horse_anim_parser.py`.

## 3. The 16-bit per-track encoding mask

Per `FUN_00dd6a30` + `FUN_00dd7b00`:

| Bits | Field |
|---|---|
| 0-1 | `trans_skip` flag (==2 → write zero translation, skip 3 reads) |
| 2-3 | `rot_skip` flag (==8 → write identity quat, skip 4 reads) |
| 4-5 | `scale_skip` flag (==0x20 → write unit scale, skip 3 reads) |
| 6 | Tz src (0=dynamic, 1=static) |
| 7 | Ty src |
| 8 | Tx src |
| 9 | Qw src — sentinel ±2.0 here triggers smallest3 W-recovery |
| 10 | Qz src |
| 11 | Qy src |
| 12 | Qx src |
| 13 | Sz src |
| 14 | Sy src |
| 15 | Sx src |

## 4. The dnap on-disk format (so far decoded)

```
0x00  4s    magic 'dnap'
0x04  f32   period_seconds  (= frames_per_period / fps)
0x08  f32   fps  (always 30 for b20_horse)
0x0C  u16   total_frames
0x0E  u16   version (0 / 2 — possibly Delta vs Wavelet selector)
0x10  u16   frames_per_period (loop length)
0x12  u16   num_tracks
0x14  u16   pad
0x16  u16   num_blocks (under-counts when last block is implicit;
                       use .header[0x0F] as authoritative)
0x18..0x40  per-anim metadata (4× sentinel 0xC5F17C5C bbox markers,
                               num_static_rot @0x34, num_static_trans @0x36,
                               and other layout hints)
0x40  u32[8] section sizes secs[0..7]
0x60..0x68  pad
0x6C  u16[] track→bone remap (length = (secs[2] - 0x6C) / 2)
secs[2]    start of compressed payload
```

Key invariant from header: `num_static_rot + num_static_trans = num_tracks`
(verified across all 27 b20_horse animations).

## 5. The acquire() function (`FUN_00451000`)

Generic resource manager lookup-with-load. On cache miss:

```c
piStack_2c = mgr.fileLoaders[fileIndex];           // per-package loader

piStack_2c->vftable[0xc](file_offset,              // read raw bytes
                        &outDataPtr, &outSize, ...);

piStack_2c->vftable[0xd](0,                         // construct resource
                        AnimResourceRsMgr,
                        hash,
                        auStack_28,                  // 16B output struct
                        bytes, size,
                        0, 0, 0);
```

**The dnap parser is inside `piStack_2c->vftable[0xd]`** — a generic
file-loader's "construct typed resource" method that dispatches based on
the type-specific manager (here, `AnimResourceRsMgr`).

## 6. The Delta dtor (`FUN_00dcca00`) — proves the runtime struct layout

```c
void hkaDeltaCompressedAnimation_dtor(this) {
    *this = hkaDeltaCompressedAnimation::vftable;     // 0x00dc9d30

    if (this[+0x4] != 0) {                            // u16 has-buffer flag
        TlsFree(this[+0x68], this[+0x6c]);            // owned data buffer
    }

    *this = hkBaseObject::vftable;                    // chain to base dtor
}
```

This **confirms** the runtime struct layout that `FUN_00dcca40` consumes:
- `+0x10/0x14`: numTracks / numFloatTracks
- `+0x24`: totalFrames
- `+0x28`: framesPerPeriod
- `+0x2c`: blockSize / 4 alignment
- `+0x48..0x5c`: per-block (rot_offset, rot_size, trans_offset, trans_size)
  pointers and integers
- `+0x68..0x6c`: owned data buffer (pointer + size)

## 7. What's still missing — find the Delta ctor

The full call chain is:

```
acquire() → fileLoader.parseBytes() → AnimResourceRsMgr.create() →
hkaDeltaCompressedAnimation::ctor(this, dnap_bytes, dnap_size)
```

The ctor is what we need. It must:
1. Set `*this = hkaDeltaCompressedAnimation::vftable` (= `0x00dc9d30`)
2. Copy header values from `dnap_bytes + 0x0c..0x18` into `this+0x10..0x2c`
3. Allocate `this[+0x68]`, copy section bytes in, set up `this+0x48..0x5c`
   pointers into the buffer for each block

**MSVC convention**: ctor + dtor are usually colocated. Dtor is at
`0x00dcca00`, sample is at `0x00dcca40`. **The ctor is most likely in
the `0x00dcc500..0x00dcc9ff` range**, immediately before the dtor.

### Two ways to find it:

**Option A** (cleanest): in Ghidra, navigate to data label
`0x00dc9d30` (`hkaDeltaCompressedAnimation::vftable`). Right-click →
"References to" → the function that **writes** this address into a
`*this` pointer is the ctor. Add it to `TARGET_FUNCTIONS`.

**Option B**: brute-force export the range. Add to your script:

```python
TARGET_FUNCTIONS += [
    "00dcc500", "00dcc600", "00dcc700", "00dcc800", "00dcc900",
    "00dcc9a0", "00dcc9c0", "00dcc9e0",
    # Or whichever Ghidra has labeled in that span.
]
```

Once we have the ctor, the parser can read on-disk dnap bytes and use
the existing `decode_bit_packed_stream()` to produce per-frame
quaternions for any animation. **Everything else is already in place.**

---

## 8. The full picture — every load-side function exported

The complete chain is now traced and decoded.

### Class registration (`FUN_00e1b630`)

```c
_DAT_01003400 = FUN_00dc9d30();           // vtable getter (returns 0x00e6f70c)
_DAT_010033f4 = "hkaDeltaCompressedAnimation";
_DAT_010033f8 = &LAB_00dc9d10;            // outer ctor
_DAT_010033fc = &LAB_00dc9cf0;            // destroy wrapper
```

### The actual vftable (17 entries, at `0x00e6f70c`)

| Slot | FUN | Notes |
|---|---|---|
| `[0]` | `FUN_00dc9e50` | scalar/vector dtor |
| `[1]` | `FUN_00c8e760` | inherited (hkBaseObject) |
| `[2]` | `FUN_00c8e770` | inherited |
| `[3]` | `FUN_00dcc1a0` | |
| `[4]` | `FUN_00dccfb0` | `StDecompressDChunk` (sample full chunk) ✅ |
| `[5]` | `FUN_00dcbeb0` | |
| `[6]` | `FUN_00dcc6e0` | |
| `[7]` | `FUN_00dcc1d0` | |
| `[8]` | `FUN_00dcbe90` | |
| `[9]` | `FUN_00dcbf10` | |
| `[10]` | `FUN_00dcbfc0` | |
| `[11]` | `FUN_00dcc060` | |
| `[12]` | `FUN_00dc9d40` | forwarder to `(this+0x18)->vmethod[3]` |
| `[13]` | `FUN_00dc9d60` | |
| `[14]` | `FUN_00dcbb40` | |
| `[15]` | `FUN_00dcbcb0` | |
| `[16]` | `FUN_00dcbea0` | |

### Outer ctor (`FUN_00dc9d10`)

```c
void hkaDeltaCompressedAnimation_ctor(this, init_flag) {
    if (this != NULL && (*this = vftable, init_flag != 0)) {
        FUN_00dcc280(this);   // inner: byte-swap pass
    }
}
```

### Destroy wrapper (`FUN_00dc9cf0`)

```c
void destroy(this) { (**this->vtable[0])(0); }
```

### Inner ctor (`FUN_00dcc280`) — big-endian → little-endian byte swap

The "loading" work is **just byte-swapping**. The actual file → struct
memcpy happens earlier (inside `FUN_00451000`'s acquire chain via the
file-loader's `vftable[0xd]`). For PC files, `this[+0x48] != 4` so the
function is a no-op — files are already little-endian on disk.

```c
if (this[+0x48] == 4 && data[0] != 0) {
    // Region 1: byte-swap u16 mask array at data+4
    for (i in this[+0x10] + this[+0x14]) {
        data[4 + i*2] = bswap16(data[4 + i*2]);
    }

    FUN_00dd7070(rot_masks, trans_masks, num_rot, num_trans, &counters);

    // Region 2: byte-swap u32 array at data + this[+0x50]
    for (i in counters[0..3] sum) data[this[+0x50] + i*4] = bswap32(...);

    // Region 3+4: parallel byte-swap at data + this[+0x34] / this[+0x38]
    for (i in counters[7..10] sum) {
        data[this[+0x34] + i*4] = bswap32(...);
        data[this[+0x38] + i*4] = bswap32(...);
    }
}
```

### Mask analyzer (`FUN_00dd7070`) — 14-int output struct

| Slot | Meaning |
|---|---|
| `[0]` | dynamic trans-channel count = `num_rot*3 - skip[trans] - static[trans]` |
| `[1]` | dynamic rot-channel count = `num_rot*4 - skip[rot] - static[rot]` |
| `[2]` | dynamic scale-channel count = `num_rot*3 - skip[scale] - static[scale]` |
| `[3]` | active float-track count = `num_trans - num_zero_masks` |
| `[4]` | trans-skip channel sum (3 per skip-flag set) |
| `[5]` | rot-skip channel sum (4 per skip-flag set) |
| `[6]` | scale-skip channel sum (3 per skip-flag set) |
| `[7]` | trans-source-bit sum (bits 6,7,8) |
| `[8]` | rot-source-bit sum (bits 9-12) |
| `[9]` | scale-source-bit sum (bits 13-15) |
| `[10]` | zero-mask track count (in float-track array) |
| `[11]` | `num_rot * 10` |
| `[12]` | `num_trans` |
| `[13]` | average bits/channel |

## 9. CRITICAL: the track-type interpretation was wrong

`num_static_rot` / `num_static_trans` in the dnap header are NOT
"static-rotation-tracks" and "static-translation-tracks". From
`FUN_00dd7070`'s loop structure + `FUN_00dd6ad0`'s differential
treatment of the two arrays:

| Field | Real meaning |
|---|---|
| `num_static_rot` (dnap +0x34) | **`num_quat_tracks`** — full bone tracks. Each has T+R+S, 16-bit mask with skip flags. |
| `num_static_trans` (dnap +0x36) | **`num_float_tracks`** — scalar float tracks (one float each). 16-bit mask = 0 means "all-default". |

That's why:
- Skip-flag masks (`0x3`, `0xC`, `0x30`) are only checked on the
  rot-track array — scalar float tracks have no T+R+S to skip.
- `FUN_00dd6ad0` does only "count zero entries" on the float-track
  array — it's just sparsity detection.

Verified: `num_quat + num_float == num_tracks` for all 27 b20_horse
animations.

`action_getup_back` has 0 quat-tracks and 39 float-tracks — likely a
special encoding where every quaternion component is stored as an
individual scalar float track instead of a packed quat.

## 10. The on-disk dnap layout (corrected)

```
0x00..0x0F  magic + period_seconds + fps + total_frames + version
0x10..0x17  frames_per_period + num_tracks + pad + num_blocks
0x18..0x40  metadata (sentinels, num_quat=+0x34, num_float=+0x36, hints)
0x40..0x60  8 u32s — these map to struct[+0x40..+0x60] and contain
            offsets into the data buffer (NOT just sizes)
0x60..0x68  pad / extra fields
0x68        start of "data buffer" (= this+0x68 in runtime struct)
0x68 + 0    4-byte data header
0x68 + 4    u16[N] encoding masks (N = num_quat + num_float)
              - first num_quat entries: bone-track masks (with skip flags)
              - next num_float entries: scalar-track masks
0x68 + ...  static reference floats (one per static-source-bit channel)
0x68 + ...  dynamic per-block delta streams
```

The "track→bone remap" interpretation at file offset `0x6C` (in earlier
versions of the parser) was **the per-track encoding mask array** —
because `data+4 = file 0x6C`. The earlier parser was reading it as
something else entirely.

## 11. State of the parser

Everything needed for delta decode is in hand:

1. **Mask reader**: file offset 0x6C, length = `num_quat + num_float`.
2. **Skip & source bit semantics**: documented per `FUN_00dd6a30` / `FUN_00dd7b00`.
3. **Static reference floats**: section pointed to by file offset
   0x44/0x48 (struct +0x34/+0x38), length from `FUN_00dd7070` counters
   `[7]+[8]+[9]+[10]`.
4. **Dynamic per-block streams**: section at file offset 0x50 (struct
   +0x50), per-block size from `secs[3..6]`.
5. **Bit-packed decode**: `decode_bit_packed_stream()` mirrors
   `FUN_00dde3c0` + `FUN_00dde310` correctly.
6. **Per-track recompose**: per-channel dispatch by 16-bit mask matches
   `FUN_00dd7b00`.

**No more Ghidra exports needed.** Remaining work is parser plumbing:
wire the mask array → static + dynamic stream locations → iterate
per-track → emit per-frame quaternions.

## 12. Reality check — what wiring revealed

When I actually wired this up in `b20_horse_anim_parser.py`, the
hypothesis "data buffer starts at file offset 0x68, masks at 0x6C"
**didn't hold**. The u16 values at file offset 0x6C come out as
sequential small integers:

| Animation | quat_masks | float_masks |
|---|---|---|
| relaxed_breathe | `[0x15, 0x15]` | `[0x01, 0x02, 0x03, …, 0x12]` (sequential 1–18) |
| relaxed_trot | `[0x24, 0x24]` | `[0x18, 0x23, 0x24, 0x24, 0x00, 0x01, …]` |
| action_getup_back | `[]` | `[0x02, 0x03, 0x04, …]` (sequential 2–N) |

Real per-track encoding masks would have varied bit patterns
reflecting different skip / static / dynamic source choices per track.
Sequential 1, 2, 3, ... with `0x15` (=21=`num_tracks` for breathe) at
the head almost certainly means **this is a remap / index table**, not
encoding masks.

### What this means

The runtime "data buffer" — where `FUN_00dcc280` does its byte-swap
and where `FUN_00dd6a30/dd7b00` consume the actual encoding masks —
**is allocated and populated separately** from a contiguous slice of
the dnap file. The conversion from on-disk dnap layout to runtime
data buffer layout is performed by the file-package loader's
`vftable[0xd]` method (the one called from `FUN_00451000`'s acquire
chain after gunzip). That function rearranges file content into the
runtime struct in a non-trivial way.

Since `FUN_0066a540` and `FUN_00d51460` (`AnimResourceRsMgr` slots
[14] and [15]/[16]) are no-op stubs, the rearrangement is happening
in some other function — most likely `FUN_0066a540`'s "real"
implementation is somewhere we haven't looked, or it's inlined into
the per-package file loader.

### What the parser exposes now

- The `track_masks` field still reads u16s at file 0x6C — labeled as
  "candidates", because we strongly suspect they're a track→stream
  remap table rather than encoding masks per se.
- `mask_stats` runs `FUN_00dd7070`'s analysis on whatever u16s we
  found there. The output is real arithmetic but the input may be the
  wrong array.
- `decode_bit_packed_stream`, `parse_track_quant`, `stream_byte_size`,
  `mask_skip_flags`, `mask_static_counts` etc. are all correct
  per-Ghidra and ready to use as soon as we know the right byte
  offsets to feed them.

### What's still needed for full per-frame decode

One of:
- The per-file-package loader's `vftable[0xd]` method (the function
  called from `FUN_00451000` after the gunzip step) — that's where
  the dnap-file-to-runtime-data-buffer transformation happens.
- Or an empirical investigation: known animation data from another
  game using the same Havok delta format that we can compare against
  byte-for-byte.

For *structural inspection* — extracting durations, event lists,
bone-track correspondence, FPS, period, total frames, block layout,
animated bone names, and the rig itself — the parser is **complete
and validated** across all 27 b20_horse animations. Per-frame
quaternion playback is the one remaining feature, blocked on the one
remaining loader function.
