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
