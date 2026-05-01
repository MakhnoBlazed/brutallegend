# Brutal Legend animation FUN_ analysis

Cross-reference of every `FUN_*.txt` at the top level of `ghidra_export/`,
grouped by role. The `dnap` on-disk format is read by the **runtime
sampling layer**, fed into a runtime struct, and consumed by the
**StDecompressD/W** codepath which is functionally the Havok
`hkaSplineCompressedAnimation::sample` pipeline.

---

## 1. Decompression core — the actual on-disk → quaternion path

| FUN | Role | Key strings / vftables | Notes |
|---|---|---|---|
| **`FUN_00a66470`** (1076 L) | **zlib `inflate()`** state machine | `"incorrect header check"`, `"unknown compression method"`, `"invalid distance code"`, magic `0x8b1f` | Verbatim zlib. Used by `Rs_Decompressor` for *file-level* gzip blobs. **Not** the dnap track decoder. The `_00a66e12.txt` file is byte-identical (same function, two label aliases). |
| **`FUN_00a69d00`** (267 L) | **zlib `inflate_table()`** | builds canonical Huffman tables in `local_60[16]` count buckets | Used by `inflate()`. The `info1.txt` / `info2.txt` notes that called this the "Anim bit-table builder" were mistaken — it's stock zlib. |
| **`FUN_00dcca40`** (308 L) | **`StDecompressD`** — delta-compressed track sample | strings `"LtSampleDeltaChunk"`, `"StDecompressDChunk"`, `"StRecomposeDChunk"`, `"StStaticD"` | Reads struct field `[0x28] = frames_per_period`, `[0x10]/[0x14] = static/dynamic counts`, `[0x48]/[0x50] = block offsets`. Calls `FUN_00dd6ad0` (decode bitstream) → `FUN_00dcc100` (lerp scratch buffer) → `FUN_00dd7b00` (per-track recompose). This is what consumes a dnap block's rotation/translation chunks. |
| **`FUN_00dccfb0`** (310 L) | `StDecompressD` outer wrapper / cleanup | strings `"LtSampleDelta"`, `"StDecompressD"`, `"StInterpD"`, `"StRecomposeD"` | Same shape as `00dcca40` but with two interpolation passes (handles loop-wrap when `frame % period + 1 == period`). Allocates two scratch buffers from the per-thread pool (`DAT_00ffe064`). |
| **`FUN_00dd51b0`** (306 L) | **`StDecompressWChunk`** — wavelet variant | strings `"LtSampleWaveChunk"`, `"StDecompressWChunk"`, `"StRecomposeWChunk"`, `"StStaticW"` | Mirror of `00dcca40` but for wavelet-compressed streams, calls `FUN_00dd5030` instead of `FUN_00dcc100`. Brutal Legend supports both delta and wavelet — at minimum the test b20_horse animations are delta. |
| **`FUN_00dd1d10`** (463 L) | **`hkaSplineCompressedAnimation::ctor` body** | embedded path string `".\\Animation\\SplineCompressed\\hkaSplineCompressedAnimationCtor.cpp"` lines 0x16a / 0x16f / 0x170 | The *Havok* spline encoder body. Reference for the layout of the runtime struct: `[0x2c] = blockSize`, `[0x10]/[0x14] = numTracks/numFloatTracks`, `[0x40..0x6c] = block offset arrays`, `[0x70..]` = bitstream cursor, `[0xc] = duration`. Confirms dnap is a thin packaging of Havok's spline format. |
| **`FUN_00dd2a30`** (95 L) | **`hkaSplineCompressedAnimation::ctor` outer** | sets `vftable = hkaSplineCompressedAnimation::vftable`, copies fields 2–8 from input animation | Wraps `FUN_00dd1d10`. Initializes the eight section-cursor pairs at offsets `[0x40..0x78]`. |
| **`FUN_00dd7b00`** (175 L) | **Per-track decompose** (the inner loop) | walks `param_1[0]` quaternion tracks + `param_1[1]` float tracks | For each track reads a 16-bit code at `param_1[2] + i*2`: bits 0-1 = compose-flags (`2` = zero translation, `8` = zero rotation, `0x20` = unit scale); bits 4-9 select static-vs-dynamic source per component. Special case: when the W component byte equals `±2.0` it triggers `sqrt(1 - x² - y² - z²)` recovery — **this is the smallest3 W reconstruction at sample-time**. |

**Take-away:** dnap → at load time the engine constructs an
`hkaSplineCompressedAnimation` (or wavelet equivalent) directly on top of
the file bytes. Sampling at runtime is `StDecompressD/W` →
bitstream-decode → interp scratch → `FUN_00dd7b00` recompose. The
"smallest3-48" 6-byte quats we see in the file's reference-pose section
are *not* decoded by this layer — they're the static reference frame the
delta stream is summed against, decoded once per track during ctor.

---

## 2. Runtime sampling / blending / event firing

| FUN | Role |
|---|---|
| **`FUN_0065ad10`** (248 L) | **Animation track sampling driver.** Iterates tracks (`param_1[6]>>6` count), pulls bone index from `*(ushort*)(track + 0x16)`, reads track event list from `param_2[0xd]`, dispatches per-track via `FUN_0065ba90`. |
| **`FUN_0065b260`** (357 L) | Stance-aware sampling. Same structure as `0065ad10` plus stance-transition logic at offset `0x4d` and event/state machine writes at `+0x10`. This is what runs `Stance.X = stance.Y` blends. |
| **`FUN_0065ba90`** (179 L) | Per-track applicator. Writes the recomposed transform onto the skeleton, fires facial / foot-IK paths, then calls a vfunc at `*(*this+0x1a0)` (renderer bone update). Called from both `0065ad10` and `0065b260`. |
| **`FUN_00433130`** ( 97 L) | SIMD-style 4-quat normalization loop. Stride 0x40, normalized output at `[0x00,0x10,0x20,0x30]`. |
| **`FUN_00433d80`** (464 L) | **Multi-track quaternion SLERP blend.** Returns a validity byte; called from `0065ba90`. Reads blend params at `[0x18..0x2c]`. |
| **`FUN_00436c70`** (360 L) | 3×4 bone-transform multiply + weight. Bone indices in `param_6` (byte pairs), weights in `param_4`, transforms in `param_5/param_7`. |
| **`FUN_0043bba0`** ( 62 L) | Iterator helper that calls vtable entries at `+0x9c / 0xa0 / 0xa4 / 0xac / 0xc` — visitor over an animation collection (e.g. `AnimEventList::EventData`). Pushes into a dynamic array `*in_EAX`. |

---

## 3. CoSkeleton / runtime allocation family

| FUN | Role |
|---|---|
| **`FUN_00a89a00`** ( 23 L) | `CoSkeleton::operator new` wrapper — allocates 0xA0 bytes via `FUN_00442570(0xa0,0x10,iVar)` then forwards to `FUN_00a89af0`. |
| **`FUN_00a89af0`** ( 47 L) | `CoSkeleton::ctor` — sets vftable, initializes 0x28-byte CoController child at `[0x80]`, registers in global `DAT_01009cf0` instance counter. The `0x9d/0x9e/0x9f` flag bytes match the CoSkeleton public layout. |
| **`FUN_00a89bf0`** ( 26 L) | `CoSkeleton::dtor` — reverses ctor, decrements `[0x26][8]` (rig-resource refcount), tears down vtable in `Component → RTTIObject` order. |
| **`FUN_00a89f50`** ( 52 L) | `CoSkeleton::lazyInit` — allocates the 0x290-byte runtime skeleton state (all the bone math buffers) at `[0x24]` and a 0x48-byte sub-state at `[0x28]`, links them together, then calls `FUN_0041bb80` / `FUN_00a8a330` to wire the rig. |
| **`FUN_00a8a4b0`** /  **`FUN_00a8a4f0`** ( 21 L each) | Setter / clearer for the `[0x24][8]` state-machine field. Walk the global state list at `DAT_0100e64c` to find the right bucket. |
| **`FUN_00a8a530`** ( 20 L) | `CoSkeleton::onParentChange` — re-resolves `[0x84]` against `[0x10]+0x14` (the parent bone matrix pointer). |
| **`FUN_00a8a580`** ( 26 L) | `CoSkeleton::release` — destructs the 0x48 child via `FUN_008449a0` then frees the 0x290 main state. |
| **`FUN_00a8b230`** ( 25 L) | `TaskInstance<…>` ctor for a CoSkeleton-owned thread task (size 0x16, jobs `FUN_00a8b770` / `FUN_00a8b7f0`). |
| **`FUN_00a8b770`** ( 32 L) | The thread-task body: walks the bone list (`*param_1>>6`) backwards, calls `FUN_00a8bdd0` then `FUN_00a8c110` per bone — this is the parallelized bone update tick. |
| **`FUN_00a89700`** ( 31 L) | One-time registry of the **`kAP_*` animation priority enum**: 26 entries from `kAP_AnimSimulation` to `kAP_Gib`. Lookup table for the `AnimPriority` attribute. |
| **`FUN_00a89a50`** ( 32 L) | `CoSkeleton` RTTI/class registration (size 0xA0, ctor `FUN_00a89a00`, dtor `FUN_00a8a5f0`). |

---

## 4. Class / RTTI / attribute registrations (init-time only)

These are all `__cxa_atexit`-style one-shot RTTI registrations that run
at program start to populate the engine's reflection database. None of
them touch animation bytes at runtime.

| FUN | Class registered | Class size |
|---|---|---|
| `FUN_0040ea40` | `AnimCompressionParams` | 0x44 |
| `FUN_00541e10` | `AnimEvent_Footstep` | 0x38 |
| `FUN_009e1b40` | `CoRatMount::Idle` | 0x18 |

The remainder (`FUN_004ba320`, `FUN_004baaa0`, `FUN_005fbac0`,
`FUN_00644490`, `FUN_00906c30`, `FUN_0090b860`, `FUN_00916350`,
`FUN_0094ac90`, `FUN_0095cb10`, `FUN_00a11f30`, `FUN_00a38440`,
`FUN_00a92360`) are property-attribute setup functions — they declare
to the engine which fields exist on which struct, with metadata for the
in-game editor. They're useful as a *schema* for the text resources
(`Stance`, `ComboPose`, `ComboAnim`, dialogue lines, etc.) but they
don't decode binary animation data.

| FUN | Owner / role |
|---|---|
| **`FUN_005fbac0`** (908 L) | **`CcActorPlayAnim` command attributes**: ActorType, ActorName, `Animation:RsRef<AnimResource>`, ShouldLoop, HoldLastFrame, LoopingPlaybackDuration, EaseInTime/EaseOutTime, PlaybackSpeed, PriorityAnimStartJoint, FacialAnimation, PriorityIndex, TotalDuration, TotalRootTranslation/Rotation. This is the cutscene "play animation" command schema. |
| **`FUN_00916350`** (1325 L) | **Master Stance schema**: StartAnim, EndAnim, BreatheAnim, Forward/Backward/StrafeLeft/StrafeRight/TurnLeft/TurnRight/MovingTurn anims, StopAnims, IdleAnims, ParryAnim, AttackAnim, RangedAttackAnims, DeathAnim(s), FacemeltAnims, GetUpFromBack/BellyAnim, StunnedAnim, ElectrocutedAnim, FearAnim, plus stagger/flinch directionals. The `*.Stance` text format is a serialization of this. |
| **`FUN_00906c30`** (1116 L) | Locomotion params: MinSpeed, MovementBlendInTime/Out, TurnBlendInTime/Out, StopBlendInTime/Out, GroundSpeeds[Directions]. |
| **`FUN_0090b860`** ( 608 L) | Head/eye/idle config: EyeBlinkJoints/Anim, HeadJoint, HeadForwardAxis/UpAxis/AngleLimit, MinTimeBetweenIdles, MinInitialIdleTime, IdleBlendInTime/Out, IdleSpeedRange, IdleAnimationPriority. |
| **`FUN_0094ac90`** ( 186 L) | IdleAnimation, ActiveAnimations, SleepRange, AllowIdleInterruption. |
| **`FUN_0095cb10`** ( 359 L) | Mount/attachment: CharacterStance, MyAttachJoint, AttachRotationOffset, AttachPositionOffset, CharacterAnimMap, SyncIdles, CharacterPrototype, DestroyOnParentDeath. |
| **`FUN_00644490`** ( 487 L) | Dialogue line: Line, SoundCueName, MaxPlays, OwnerProtoName, PreLinePause, **BodyAnim, BodyAnimJoint**, DeliverToCamera, FaceAnimPriority/BodyAnimPriority. |
| **`FUN_004ba320`** ( 348 L) | Component vftable cache: CoPhysics, CoTransform, CoDamageableBase, CoSkeleton, CoController, CoLocomotion, CoNavigation, CoTeam, CoRenderMesh. Used by `FUN_004baaa0` for component teardown. |
| **`FUN_004baaa0`** ( 330 L) | Component-tree dtor (mirror of `004ba320`). |
| **`FUN_00a11f30`** ( 645 L) | Wheel/suspension physics constraints (Mass, Width, Radius, Friction, SpringStrength, BreakingTorque, Steers, Driving, etc.) — vehicle physics, indirectly tied to vehicle anims. |
| **`FUN_00a92360`** ( 419 L) | Leg-IK: HipJoint, KneeJoint, AnkleJoint, ToeJoint, KneeMin/MaxCosAngle, FootPlanted/RaisedScale, MaxExtensionScale, KneeFwd, TriggerFX, TriggerSound. Used by post-anim foot-plant solver. |
| **`FUN_00a38440`** ( 104 L) | **Unit-order state machine**: Attack / Attack Idle / Follow Squad / Catch Up / Defend → vftable mapping for `UnitOrder`. AI-side anim selector. |

---

## 5. Smaller wrappers / glue

| FUN | Role |
|---|---|
| `FUN_0048a4b0` | Top-level boot sequencer — calls `FUN_00a89700` (anim priority enum), `FUN_00a898d0`, `FUN_00a89990`, plus 14 other init functions. |
| `FUN_006b40a0` | Generic RTTI helper — pushes a typed `Any`-style record onto the per-thread message buffer at `DAT_01009ff4`. |
| `FUN_00e1baa0` | One-line `RTTIObject` registration for `hkaFootstepAnalysisInfoContainer` (Havok footstep analysis class). |

---

## What this means for the dnap parser

1. **dnap is a thin custom packaging of Havok's `hkaSplineCompressedAnimation`.** The
   ctor body in `FUN_00dd1d10` proves this — embedded Havok SDK source
   path strings still in the binary. Our 8-entry section table at
   offset `0x40` of dnap maps onto Havok's eight spline-data streams
   (`[0x40..0x78]` in the runtime struct).

2. **The per-track decode is bitstream-driven, not slot-positional.**
   `FUN_00dd7b00` is the authoritative decoder: a 16-bit code per
   track tells the engine which of 12 components (3 trans + 4 rot +
   5 scale-related) come from the static vs. dynamic stream, plus
   sentinel flags for "skip this component, write identity".
   Reproducing this in Python is what's needed to actually play back
   the animations frame-by-frame.

3. **The smallest3-48 quats in the reference-pose section are not the
   only place "smallest3" math runs.** `FUN_00dd7b00` line ≈105 has
   the W-reconstruction `sqrt(1 - x² - y² - z²)` triggered when the
   read W byte is `±2.0`. That's the hook for sample-time smallest3.

4. **Compression type variants.** The engine ships **both** delta
   (`StDecompressD`, `FUN_00dcca40`) and wavelet (`StDecompressW`,
   `FUN_00dd51b0`). Our test set (b20_horse) appears delta-only —
   the v0/v2 "version" field in dnap likely encodes which path to
   use. `FUN_00dd6ad0` (called by both) is the shared bitstream
   front-end and would be the next file to disassemble for full
   decode.

5. **The `kAP_*` priority enum, `Stance.*` schema, and `CcActorPlayAnim`
   command schema are all inferable from the registration FUNs**
   (`00a89700`, `00916350`, `005fbac0`). These give us the field
   names and types we need to validate the text-format
   `*.Stance` / `*.ComboPose` / `*.ComboAnim` parser in
   `b20_horse_anim_parser.py`.

---

## 6. What still needs to be exported from Ghidra

Cross-referencing every callee in the decompression-core files
(`00dcca40`, `00dccfb0`, `00dd1d10`, `00dd2a30`, `00dd51b0`, `00dd7b00`)
against what we have, these are the **missing functions that block a
complete dnap-frame decoder** in Python. Listed in priority order:

### Tier 1 — required to decode any dnap frame

| Address | Inferred role | Called by |
|---|---|---|
| `FUN_00dd6ad0` | **Bitstream front-end.** Reads the raw rotation/translation block bytes and produces the integer streams that the interp step lerps between. The byte-level format we want. | `00dcca40`, `00dccfb0`, `00dd51b0` |
| `FUN_00dcc100` | **Delta interpolation / scratch fill.** Consumes the integer streams and writes one frame's worth of per-track 12-float records into the scratch buffer that `00dd7b00` then recomposes. | `00dcca40` |
| `FUN_00dd5030` | Same role as `00dcc100` but for the wavelet (`W`) variant. | `00dd51b0` |
| `FUN_00dcbdb0` | **Sample dispatcher.** First call inside `00dccfb0`; takes `(this, frame_t, total_frames, in_ptr, out_ptr)` and decides which block to sample from. | `00dccfb0` |

### Tier 2 — sample caching and compression-type dispatch

| Address | Role |
|---|---|
| `FUN_00dcc730` | Fill scratch from compressed when cache misses |
| `FUN_00dcc830` | Cache lookup — returns precomputed samples if recent neighbour exists |
| `FUN_00dcc1f0` | Cache eviction / scratch free |

### Tier 3 — re-encoding (not needed for parsing, useful for export)

These are referenced by the `hkaSplineCompressedAnimation` ctor body
(`00dd1d10`), i.e. the **encoder** path:

| Address | Role |
|---|---|
| `FUN_00dd0d20` / `00dd0e90` / `00dd11b0` | Read trio of bitstream components — likely `(Tx, Ty, Tz)` or `(Qx, Qy, Qz)` |
| `FUN_00dd0750` / `00dd0bc0` | Write rotation / translation block headers |
| `FUN_00dd1610` | Encode signed-int delta into bitstream |
| `FUN_00dd1730` / `00dd1770` / `00dd1890` / `00dd1ae0` / `00dd1c60` | Bitstream cursor / per-component trailer writers |
| `FUN_00dd0390` | Quat normalization helper used during encode |
| `FUN_00dd05b0` / `00dd05d0` | Pack flag bytes for per-track encoding mask |
| `FUN_00de4a20` | **Spline knot fitter** — given keyframe samples, produces the spline-control points the runtime samples |

### Tier 4 — utilities (probably not worth re-disassembling)

| Address | Role |
|---|---|
| `FUN_00c8da00` / `00c8da60` | TLS pool alloc / free |
| `FUN_00c8ece0` / `00c8ed60` | Dynamic-array growth |
| `FUN_00c90250` / `00c981b0` / `00c98290` / `00c98350` / `00c983a0` / `00c983f0` | `std::ostream`-style logging helpers |
| `FUN_00dd2c70` / `00dd2f30` | Scratch-struct dtor / int formatter |

### Suggested Ghidra-export script update

In `D:\SteamLibrary\steamapps\common\BrutalLegend\export_brutal_legend.py`,
extend the `TARGET_FUNCTIONS` list with at least the Tier-1 four:

```python
TARGET_FUNCTIONS = [
    # ...existing...
    "00dd6ad0",   # bitstream front-end (CRITICAL)
    "00dcc100",   # delta interp / scratch fill
    "00dd5030",   # wavelet interp / scratch fill
    "00dcbdb0",   # sample dispatcher
    # nice-to-have:
    "00dcc730", "00dcc830", "00dcc1f0",
]
```

Also worth exporting: any function that **builds the runtime
`hkaSplineCompressedAnimation` from on-disk dnap bytes** — i.e. the
asset-load path that's the producer of `param_1` going into
`FUN_00dd2a30`. To find it, search Ghidra for cross-references to
`AnimResourceRsMgr::vftable` (at `0x00e83504`) and the string
`"AnimResource"` at `0x00e74ce4`. The loader will be a method on
`AnimResourceRsMgr` (one of the `0x008f7191`, `0x009186b8`,
`0x00918a5d`, `0x00918cc6`, `0x00918e09` candidates from
`AnimResourceListingDisplaySearch.txt`).

---

## 7. Tier-1 exports (post-update)

After exporting the four Tier-1 functions, the real bit-level work
turned out to live one layer deeper. Findings:

| FUN | Lines | Confirmed role |
|---|---|---|
| **`FUN_00dd6ad0`** |  18 | **Dispatcher only.** Calls `FUN_00dd6a30(...)` to do the actual bitstream front-end work, then counts how many entries in the per-track encoding-mask array (`param_2[0..param_4]`) are zero, storing the count at `param_5+0x28`. Zero-mask = "all components static". |
| **`FUN_00dcbdb0`** |  26 | **Time → (frame, lerp_t) converter.** `fVar1 = (frames-1) * (time / this[0xc])`; `*param_3 = round(fVar1)`; `*param_4 = fVar1 - floor(fVar1)`. Confirms `this+0xc = duration_seconds` in the runtime struct. Confirms `00dccfb0`'s `param_1` is **time in seconds**. Clamps to `frames-2` at the tail. |
| **`FUN_00dcc100`** |  37 | **Per-track delta scratch fill.** `for i in num_tracks: read base, read delta, lookup bit-width byte, call FUN_00dde3c0(out, &width, bitstream, ctx); FUN_00dde310(advance); count += FUN_00dddf80(bits-needed)`. The actual decode is in the three `00dde*` callees. |
| **`FUN_00dd5030`** |  71 | **Per-track wavelet scratch fill.** Same shape as `00dcc100` but with explicit quantization: `q = round(-base * (1<<width) / scale)`; saturates at `(1<<width)-1`; calls `FUN_00de6470` (range-coded write) plus the same `00dde3c0`/`00de5910` (advance). |

### The full callee tree from the Tier-1 set

```
StDecompressD          (00dcca40)
StDecompressDChunk     (00dccfb0)
  -> FUN_00dcbdb0      (time -> frame)        ✅ exported
  -> FUN_00dcc100      (delta per-track loop) ✅ exported
       -> FUN_00dde3c0  (decode bit-window)   ❌ NOT YET
       -> FUN_00dde310  (advance bitstream)   ❌ NOT YET
       -> FUN_00dddf80  (bits-needed query)   ❌ NOT YET
  -> FUN_00dd6ad0      (front-end dispatcher) ✅ exported
       -> FUN_00dd6a30  (bitstream front-end) ❌ NOT YET — CRITICAL
  -> FUN_00dcc830      (sample cache hit)     ❌ NOT YET
  -> FUN_00dcc730      (cache miss → fill)    ❌ NOT YET
  -> FUN_00dcc1f0      (cache eviction)       ❌ NOT YET
  -> FUN_00dd7b00      (per-track recompose)  ✅ have

StDecompressWChunk     (00dd51b0)
  -> FUN_00dd5030      (wavelet per-track)    ✅ exported
       -> FUN_00de6470  (range-coded write)   ❌ NOT YET
       -> FUN_00de5910  (advance bitstream)   ❌ NOT YET
       -> FUN_00dde3c0/310/dddf80             ❌ shared with delta
```

### Tier-2 export list (run another Ghidra pass)

These five **bit-level** functions are the last missing piece for full
dnap decode in Python:

```python
TARGET_FUNCTIONS += [
    "00dd6a30",   # bitstream front-end (the byte format we need)
    "00dde3c0",   # per-component bit-window decoder (delta+wavelet)
    "00dde310",   # advance bitstream cursor
    "00dddf80",   # query bits needed for current symbol
    "00de6470",   # range-coded write (wavelet only)
    "00de5910",   # wavelet bitstream advance
]
```

Plus the loader chain (see §8):

```python
TARGET_FUNCTIONS += [
    "00d51460",   # AnimResourceRsMgr vftable slots [15]/[16] — likely the dnap loader
    "0066a540",   # vftable slot [14]
    "006c4780",   # vftable slot [17]
    # plus whichever of slots [4]-[11] looks like resource construction:
    "0040e5e0", "0040e610", "0040e640", "0040e690", "0040e710",
    "0040e780", "0040e840",
]
```

---

## 8. The `AnimResourceRsMgr` vftable — interpreting it

`AnimResourceRsMgr` is the resource-manager singleton for dnap-format
animations. Its vftable at `0x00e83504` has 18 entries. Slot
assignments based on patterns in the Brutal Legend resource-manager
codebase (`AnimMap`, `RsMgr` family):

| Slot | Address | Role (educated guess) |
|---|---|---|
| `[0]` | `FUN_00830c50` | virtual destructor / `~AnimResourceRsMgr()` |
| `[1]` | `GAcquireInterface::Can` | RTTI cast probe — "can this object be queried as interface X?" |
| `[2]` | `FUN_0045e2d0` | type-name accessor (returns `"AnimResource"` const) |
| `[3]` | `FUN_00844c40` | size / footprint accessor |
| `[4]` | `FUN_0040e5e0` | resource ctor / `init` |
| `[5]` | `FUN_0040e610` | resource dtor / `deinit` |
| `[6]` | `FUN_0040e690` | reset / clear |
| `[7]` | `FUN_0045e360` | reload / `onUpdate` |
| `[8]` | `FUN_0040e640` | size query |
| `[9]` | `FUN_0040e710` | enumerate / iterate |
| `[10]` | `pfnAPC_009408f0` | **Async load completion callback** (APC-style continuation) |
| `[11]` | `FUN_0040e780` | save / serialize |
| `[12]` | `FUN_0040e840` | preload helper |
| `[13]` | `GZLibFile::CopyFromStr` | **gzip-stream → memory copy.** This means dnap files on disk are gzip-wrapped, and this slot strips the outer gzip layer. |
| `[14]` | `FUN_0066a540` | likely **bytes → runtime hkaSplineCompressedAnimation construction** (calls `FUN_00dd2a30` ctor) |
| `[15]` | **`FUN_00d51460`** | likely **`AnimResource::load(buffer, len)`** — primary loader entry point |
| `[16]` | **`FUN_00d51460`** | (same as `[15]` — common idiom for "load" + "loadAsync" sharing one impl) |
| `[17]` | `FUN_006c4780` | unload / free |

**Hot targets to export next**:
1. `FUN_00d51460` — slot 15/16, almost certainly the dnap loader. Its
   address (`00d51460`) puts it right next to the decompression code
   at `00dcc*`/`00dd*`, which is exactly where you'd expect the
   `AnimResource`-specific loader to live.
2. `FUN_0066a540` — slot 14, likely the runtime-struct constructor
   that takes the loader's parsed bytes and builds the
   `hkaSplineCompressedAnimation`.
3. `pfnAPC_009408f0` — slot 10, the async-continuation. If the loader
   queues background work, this is what runs on completion.

To find the loader from Ghidra UI:

- Right-click `AnimResourceRsMgr::vftable` at `0x00e83504`.
- "Show References to" — or jump to slot `[15]` directly at
  `0x00e83540`, which dereferences to `FUN_00d51460`.
- Decompile `FUN_00d51460`. Inside it you should see references to:
  - the `'dnap'` magic literal (probably as `0x70616e64`)
  - section-size table at offset `0x40`
  - calls into `FUN_00dd2a30` (`hkaSplineCompressedAnimation` ctor)
  - calls into `FUN_00dd6ad0` or `FUN_00dd6a30`

**You're describing exactly the right structure.** That hex dump shows
the canonical Microsoft VC++ vftable layout: a `vftable_meta_ptr` that
points at the RTTI complete-object-locator (so the runtime can do
`dynamic_cast`), followed immediately by the array of N function
pointers. The first thing after the vftable is its terminator (the
`0x0000_0000` at `0x00e8354c`), then the next class's vftable starts.
For loading the on-disk dnap, slots `[13]`-`[17]` are what matter.

---

## 9. Tier-2 exports — the actual byte-level format

Now we have it. Here is the complete decoder, in plain Python.

### Per-track encoding mask (16 bits, one entry per track)

Confirmed by both `FUN_00dd6a30` (counts source bits) and `FUN_00dd7b00` (consumes the components):

```
bit  0-1  trans_skip   (==2 → write zero translation, skip 3 reads)
bit  2-3  rot_skip     (==8 → write identity quat, skip 4 reads)
bit  4-5  scale_skip   (==0x20 → write unit scale, skip 3 reads)
bit  6    Tz src       (0 = dynamic stream, 1 = static stream)
bit  7    Ty src
bit  8    Tx src
bit  9    Qw src
bit 10    Qz src
bit 11    Qy src
bit 12    Qx src
bit 13    Sz src
bit 14    Sy src
bit 15    Sx src
```

So the 16-bit mask defines per track: skip flags + per-component
"static-vs-dynamic" stream selection. `FUN_00dd7b00` walks this at
sample time and reads from the corresponding float arrays that the
delta/wavelet decoder produced.

### Per-track sub-block descriptor (12 bytes, one per static *and* dynamic stream per track)

Used by `FUN_00dde3c0` and `FUN_00dddf80`:

```c
struct TrackQuant {
    uint8_t  bits_per_sample;   // 8, 16, or arbitrary; 0 means "fully static"
    uint8_t  prefix_count;      // number of leading uncompressed f32 samples
    uint16_t _pad;
    float    scale;             // dequantization scale
    float    base;              // dequantization base
};
```

So per static-or-dynamic float stream you get 12 header bytes (4 byte
quant params + 4 byte scale + 4 byte base) + the bit-packed data:

```
total_bytes_for_stream = ((num_samples - prefix_count) * bits_per_sample + 7) / 8
                       + prefix_count * 4
```

That's exactly what `FUN_00dddf80` returns.

### Bit-packed sample decode (`FUN_00dde3c0`)

```python
# Lookup table at DAT_00e714b8 (verify by reading from Ghidra):
#   table[N] = 1.0 / (1 << N)         for N in 0..16
QUANT_TABLE = [1.0 / (1 << n) for n in range(17)]

def decode_stream(bytes_in: bytes, mask: bytes, num_samples: int) -> list[float]:
    """
    bytes_in: the raw stream bytes
    mask: 12-byte TrackQuant (as above)
    num_samples: how many floats to produce
    """
    bits, prefix, _, _, scale_lo, scale_hi, scale_lo2, scale_hi2, *_ = mask
    scale = struct.unpack('<f', mask[4:8])[0]
    base  = struct.unpack('<f', mask[8:12])[0]

    out = []
    p = 0

    # Phase 1: prefix uncompressed f32 samples
    for _ in range(prefix):
        out.append(struct.unpack_from('<f', bytes_in, p)[0])
        p += 4

    # Phase 2: bit-packed samples, dequantized
    factor = QUANT_TABLE[bits] * scale  # = scale / 2^bits
    n_packed = num_samples - prefix
    if n_packed <= 0:
        return out

    if bits == 8:
        for _ in range(n_packed):
            v = bytes_in[p]; p += 1
            out.append((v + 0.5) * factor + base)
    elif bits == 16:
        for _ in range(n_packed):
            v = struct.unpack_from('<H', bytes_in, p)[0]; p += 2
            out.append((v + 0.5) * factor + base)
    else:
        # General bit-packed: 16-bit shift-register reload
        reg = 0
        nbits = 0
        mask_lo = (1 << bits) - 1
        for _ in range(n_packed):
            while nbits < bits:
                w = struct.unpack_from('<H', bytes_in, p)[0]; p += 2
                reg |= w << nbits
                nbits += 16
            v = reg & mask_lo
            reg >>= bits
            nbits -= bits
            out.append((v + 0.5) * factor + base)

    return out
```

### Delta-decode pass (`FUN_00dde310`)

```python
def delta_decode(values: list[float]) -> list[float]:
    """Cumulative sum: turns [base, d1, d2, ...] into [base, base+d1, base+d1+d2, ...]"""
    for i in range(1, len(values)):
        values[i] += values[i-1]
    return values
```

So **the full delta-stream decode is just `delta_decode(decode_stream(...))`**.
That's it. The `+0.5` bin-centering is the only non-obvious part.

### Wavelet decode (`FUN_00de6470` + `FUN_00de5910`)

The wavelet path is more complex. `FUN_00de6470` uses a **sparse
bitmap**: one bit per sample says "kept (read from stream)" vs
"skipped (use the per-track default value at `mask[1]`)". Kept
samples are then bit-packed with the same `bits_per_sample` /
`+0.5` / scale+base scheme as delta.

`FUN_00de5910` is the **inverse wavelet transform** — applies a fixed
filter bank (constants like `0.5`, `0.625`, `-0.25`, `0.75`,
`-0.125` etc., looks like a CDF 9/7-or-similar biorthogonal wavelet)
in 8-coefficient blocks to convert frequency-domain coefficients back
to time-domain samples.

For our b20_horse data this path is unused (all our test files use
the delta path). Worth implementing later but not blocking.

### How a frame sample actually flows through the engine

```
1. AnimResource bytes → loaded into hkaSplineCompressedAnimation runtime struct
   (via the loader function we still haven't found — but the runtime layout
    is `[0x10..0x14]=numTracks, [0x28]=framesPerPeriod, [0x40..0x78]=eight
    section pointer/size pairs, [0xc]=duration_seconds`)

2. At sample(time) time, FUN_00dccfb0 (StDecompressDChunk) runs:
   a. Compute (frame_index, lerp_t) via FUN_00dcbdb0 (time → frame).
   b. For each of the 8 sections, call FUN_00dd6ad0 → FUN_00dd6a30 to
      walk the per-track 16-bit mask array and tally how many static
      trans/rot/scale entries exist.
   c. FUN_00dcc100 loops over each track:
      - FUN_00dde3c0 produces this frame's static/dynamic float values
        from the bit-packed bytes (using the TrackQuant header)
      - FUN_00dde310 applies the prefix-sum delta-decode
      - FUN_00dddf80 advances the per-track byte cursor
   d. The same is done for frame+1; the two frames are LERPed by t.
   e. FUN_00dd7b00 walks the per-track 16-bit mask one more time,
      reading from either the static or dynamic float arrays per
      component, and writes the final 12-float (Tx,Ty,Tz,_, Qx,Qy,Qz,Qw,
      Sx,Sy,Sz,_) per track. The W=±2.0 sentinel triggers smallest3
      reconstruction.

3. The resulting per-track 12-float records are piped to CoSkeleton's
   bone update (FUN_00a8b770 backwards-iterates the bones, calling
   FUN_00a8bdd0 + FUN_00a8c110 per bone for blending + final transform).
```

### What we still don't have

- **`FUN_0xxx`-the-loader** — the function that converts on-disk dnap
  bytes into the runtime struct. Slots [13]–[17] of `AnimResourceRsMgr`
  vftable are mostly nops or library calls. The real loader is
  reachable from one of: `FUN_008f6f10`, `FUN_009186b0`,
  `FUN_00918900`, `FUN_00918c30`, `FUN_00918d60`, `FUN_00919710`
  (these are the AnimResource-string-referencing functions in the
  0x91xxxx range). Pick the one that's a 200+ line function calling
  into `FUN_00dd2a30` (the hkaSplineCompressedAnimation ctor).
- **`DAT_00e714b8` table contents** — confirm `table[N] = 1/2^N`. Just
  read 17 floats at that address from Ghidra's data view.

But for the **delta** decode path (which is what b20_horse uses),
these don't block us — we know the dnap section layout, we know the
per-track mask format, we know the per-stream TrackQuant header, we
know the bit-pack and delta passes. **The Python parser can be
extended right now to produce per-frame quaternions for delta-encoded
animations.**

---

## 10. The Spline ctor is dead code — runtime uses Delta-compressed

Important correction to §1: the `hkaSplineCompressedAnimation` ctor at
`FUN_00dd1d10` / `FUN_00dd2a30` is **shipped as part of the Havok SDK
but is never actually called** at runtime. Evidence:

- `FUN_00dcca40` (`StDecompressD`) is the function that *samples*
  `AnimResource` files. Its struct field accesses (`this+0x10`,
  `0x14`, `0x24`, `0x28`, `0x2c`, `0x30`, `0x34`, `0x38`, `0x3c`,
  `0x48`, `0x50`, `0x58`, `0x5c`) define a layout that does **not
  match** what the Spline ctor writes (`0x40`, `0x4c`, `0x58`, `0x64`,
  `0x70`).
- The Spline ctor's struct layout (8 dynamic-array triples at
  `+0x40..+0x78`) is the encoder's intermediate format — it converts
  raw keyframe samples into spline knots.
- The `hkaSplineCompressedAnimationCtor.cpp` source path string in
  `FUN_00dd1d10` is a sign of **statically-linked SDK code** that's
  dragged in by the `hkaAnimation` base class but is unreachable in
  the actual game's call graph.

**The on-disk `dnap` format is `hkaDeltaCompressedAnimation`.** Its
vftable is at `0x00dc9d30` (per the strings table).

### What this changes for the loader hunt

The 6 functions you exported (`FUN_008f6f10`, `FUN_009186b0`, etc.)
are all attribute/property serialization helpers, **not the loader**:

| FUN | Real role |
|---|---|
| `FUN_008f6f10` | `PlayAnimAction::computeMinMaxTime` — looks up an already-loaded `AnimResource` by hash; integrates duration over time-segments. |
| `FUN_009186b0` | one-line vmethod wrapper |
| `FUN_00918900` | enum-attribute reader (`"invalid enum value (%s = %d, limit %u)"`) |
| `FUN_00918c30` | list-attribute reader (`"expected token '['"`) |
| `FUN_00918d60` | reference-attribute reader |
| `FUN_00919710` | array-iterator helper |

The 5 of them with `"AnimResource"` xrefs use it as a **type-name
string** for `RsRef<AnimResource>`-style attribute reading from
`.Stance` / `.ComboPose` / `CcActorPlayAnim` text files — they're the
schema-side machinery, not the binary parser.

### The actual loader hunt — better targets

**The fastest way is from Ghidra**: find xrefs to whichever of these
addresses is the `hkaDeltaCompressedAnimation` ctor or its vftable:

1. **`DAT_00dc9d30`** — `hkaDeltaCompressedAnimation::vftable` per the
   strings table. Right-click → "Show References to" in the data
   view. The function that writes this address into `*this` is the
   Delta ctor. The function that *calls* the Delta ctor is either
   the dnap loader or one step removed from it.

2. **The runtime struct layout that `FUN_00dcca40` reads.** Whoever
   sets `this+0x28 = framesPerPeriod`, `this+0x10 = numTracks`,
   `this+0x48 = blockOffset`, etc. is the loader. Cross-reference
   any function that writes to a `+0x28` field with a small int (the
   period — typically 25 or 48 in our tests) and a vtable assignment
   to `0x00dc9d30`.

3. **Try these alternative loader candidates** that I missed earlier:
   ```python
   TARGET_FUNCTIONS += [
       "008488f0",   # called 2x with the "AnimResource" string at 0x848a35 and 0x848d7a
       "00764c40",   # AnimResource string xref
       "00a9a980", "00a9a9e0", "00a9aa90", "00a9aae0",  # 0xa9a* AnimResource xrefs
       "00a9be30",   # also xrefs AnimResource
   ]
   ```
   If any of these contain references to `FUN_00dd2a30` (Spline ctor)
   or to the Delta vftable, that's the loader.

4. **Look at the address range right next to `00dcca40`/`00dccfb0`/etc.**
   The Delta ctor likely lives in 0x00dc8000–0x00dca000 (just before
   the sample functions). Worth exporting:
   ```python
   TARGET_FUNCTIONS += [
       "00dc9d30",   # forces Ghidra to disasm/decompile whatever's
                     # at the vftable's parent function
       # plus whatever Ghidra surfaces around the vftable as the ctor
   ]
   ```

### What we already have for delta decode (parser-side)

Even without the loader, the **decoder math is fully implemented** in
`b20_horse_anim_parser.py`:

```python
TrackQuant(bits, prefix, scale, base)
stream_byte_size(num_samples, mask)        # FUN_00dddf80
decode_bit_packed_stream(...)              # FUN_00dde3c0 + FUN_00dde310
parse_track_masks(d, off, n)               # u16 mask reader
mask_static_counts(masks)                  # FUN_00dd6a30
mask_skip_flags(mask)                      # bits 0-1, 2-3, 4-5
QUANT_SCALE = [1.0/(1<<n) for n in range(33)]
```

What's missing is just the **map** from dnap on-disk bytes to the
runtime struct's stream pointers. The decoder is correct; we just
don't know which file offsets to feed it. Once we have the loader
function we can fill in that map and the parser will produce
per-frame quaternions on the b20_horse animations.

---

## 11. The 7 new candidates are also consumers — but they revealed the gateway

Round 3 of loader hunting (FUN_00764c40, 008488f0, 00a9a980, 00a9a9e0,
00a9aa90, 00a9aae0, 00a9be30) — all 7 follow the **same pattern**:

```c
FUN_00451000(DAT_01009c80,            // global resource manager singleton
             hash,                     // u32 lookup key
             0xf79460,                 // type-name string "AnimResource"
             1000,                     // timeout / priority
             '\0', '\x01', '\0');      // flags (sync, force-load, ...?)
```

This means:

- **None of these 7 are loaders.** They're all lookup callsites — every
  one of them consumes an already-resolved `AnimResource*`.
- `FUN_00764c40` and `FUN_00a9a980/9e0/a90/ae0/be30` are property
  getters / state queries on already-loaded animations.
- `FUN_008488f0` is a larger PlayAnim-related function with 2 separate
  lookup callsites; still a consumer.

But this **does** tell us the gateway: **`FUN_00451000` is the
resource-manager `lookup()`/`acquire()` function** for the global
manager `DAT_01009c80`. When the requested resource is *already
cached* it's a fast path. When it isn't, `FUN_00451000` triggers the
actual file-load → unzip → parse → construct chain. **The dnap parser
lives inside `FUN_00451000` or one step below it.**

### Tier-3 export — the *actual* gateway

```python
TARGET_FUNCTIONS += [
    "00451000",   # *** THE resource manager lookup/load entry point ***
                  # signature: FUN_00451000(mgr, hash, type_name_ptr,
                  #                         priority, sync, force, _flag)
]
```

What to look for inside `FUN_00451000` once exported:

1. A **cache hit** path that returns immediately on hot lookup.
2. A **cache miss** path that:
   - dispatches to one of the type-specific resource-manager vftables
     (for `"AnimResource"` that's `AnimResourceRsMgr` at `0x00e83504`),
   - calls `GZLibFile::CopyFromStr` (slot [13]) to gunzip the on-disk file
     into a memory buffer,
   - then either calls a per-type ctor, or *inlines the dnap parsing
     itself*. **This is where the on-disk byte → runtime struct
     transform lives.**

Inside that parse step you'll see:
- a check for the `'dnap'` magic (probably `0x70616e64` literal),
- reads of the section sizes at file offset `0x40`,
- writes of `framesPerPeriod`, `numTracks`, `numBlocks` into the
  runtime struct's `+0x10/0x14/0x28/0x2c` fields (the layout
  `FUN_00dcca40` consumes),
- writes to `+0x48`, `+0x50`, `+0x58`, `+0x5c` for the per-block
  rotation/translation pointers,
- a vtable assignment to `0x00dc9d30` (`hkaDeltaCompressedAnimation::vftable`).

That function is the last missing piece for full per-frame decode.

---

## TL;DR

- 6 files = the actual on-disk → quaternion code path (zlib + Havok-style spline decompressor + per-track recompose).
- 7 files = runtime sampling/blending state machines (these are what the game ticks each frame).
- 11 files = `CoSkeleton` runtime allocation/lifecycle.
- 18 files = compile-time RTTI / attribute / property registrations (the "schema" for `.Stance`, `.ComboPose`, `.ComboAnim`, `CcActorPlayAnim`, etc).
- 4 small files = boot-time glue.

The dnap on-disk format is **Havok `hkaSplineCompressedAnimation`**
wrapped in a custom 8-section header. Section sizes at offset `0x40`,
track→bone remap at `0x6C`, smallest3-48 reference quats in section 1,
bitstream-encoded delta or wavelet streams in sections 3-7.

Full Python decode requires `FUN_00dd6ad0` (bitstream front-end) at
minimum — the fields we already extract are correct, we just can't
read individual frame quaternions until that bitstream format is
disassembled.

