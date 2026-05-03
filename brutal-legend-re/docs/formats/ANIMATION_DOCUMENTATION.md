# Brutal Legend Ghidra exports — quick reference

This is a **flat reference** of every `FUN_*.txt`, `DAT_*.txt`, and
`thunk_*.txt` file in this folder. It tells you in one line what each
function/data is, whether it's live code, and which subsystem it belongs to.

For deep technical analysis see [`ANIMATION_FUN_ANALYSIS.md`](ANIMATION_FUN_ANALYSIS.md).
For practical usage see [`HANDOFF.md`](HANDOFF.md).

**Legend** (status column):
- ✅ live & relevant to dnap animation
- 🔧 utility, called from animation code
- 💀 dead code (Havok SDK boilerplate that never runs)
- 📋 schema / class registration (init-time only)
- ⚙️ unrelated game subsystem (Effect, DUIMovie, Physics, UI, etc.)

**Address range cheat sheet:**
- `0x00400000–0x00500000` — early game systems, attribute schemas
- `0x00500000–0x009f0000` — main game logic
- `0x00a30000–0x00d80000` — game / Havok runtime mix
- `0x00cad000–0x00cbf000` — RTTI / packfile machinery (mostly dead)
- `0x00dc0000–0x00de9000` — Havok animation runtime (mostly dead, but has the format spec we need)
- `0x00e1b000–0x00e1c000` — class registration functions

---

## §1 Decompression core (live or near-live)

| FUN | Role | Status |
|---|---|---|
| `00a66470_00a66470` | **zlib `inflate()`** state machine — live: handles all gzip/deflate decompression | ✅ |
| `00a66470_00a66e12` | byte-identical alias of above (Ghidra found two label addresses) | ✅ |
| `00a69d00_00a69d00` | **zlib `inflate_table()`** — Huffman table builder | ✅ |
| `00dcca40` | `StDecompressD` — Havok delta sampler. Unused by BL (vftable-only ref) | 💀 |
| `00dccfb0` | `StDecompressDChunk` — chunk variant of above | 💀 |
| `00dd51b0` | `StDecompressW` — Wavelet sampler | 💀 |
| `00dd59a0` | Wavelet vftable[4] — same fate | 💀 |

---

## §2 Spline-compressed animation format (the dnap format spec)

These functions describe the on-disk format of dnap files. They're all
"dead" (registered with the class system but never called for sampling
— BL has its own custom loader inlined elsewhere) but their **bodies
are correct format documentation**.

### Class registration (init-time only)

| FUN | Role |
|---|---|
| `00e1b630` | Registers `hkaDeltaCompressedAnimation` with class system 📋 |
| `00e1b7f0` | Registers `hkaSplineCompressedAnimation` 📋 |
| `00e1b750` | Registers `hkaSplineCompressedAnimationTrackCompressionParams` 📋 |
| `00e1b700` | Registers another animation-param class 📋 |
| `00e1baa0` | Registers `hkaFootstepAnalysisInfoContainer` 📋 |
| `00e1bbc0` | Registers more animation params 📋 |
| `00e1bc60` | Registers `hkaAnimation` base class 📋 |
| `00e1c340` | Registers another anim type 📋 |
| `00e16210` | Registers `hkxSparselyAnimatedStringStringType` 📋 |

### Outer ctors (set vtable, dispatch to inner)

| FUN | Class | Inner ctor |
|---|---|---|
| `00dc9d10` | `hkaDeltaCompressedAnimation::ctor` | calls `00dcc280` 💀 |
| `00dca060` (in `00dcca060.txt`) | `hkaSplineCompressedAnimation::ctor` | calls `00dd1a00` 💀 |
| `00dd2a30` / `00dd2bd0` | Spline ctor (encoder variant, takes raw input data) | calls `00dd1d10` 💀 |
| `00dca130` (referenced) | `hkaWaveletCompressedAnimation::ctor` | calls `00dd4b00` 💀 |

### Vtable accessors (return vftable addresses)

| FUN | Returns |
|---|---|
| `00dc9cf0` | Destroy wrapper for Delta — calls vmethod[0] 🔧 |
| `00dc9d40` | vmethod[12] of Delta — forwarder 💀 |
| `00dc9d60` | vmethod[13] of Delta — same 💀 |
| `00dc9d90` | small Delta helper 💀 |
| `00dca080` | returns `hkaSplineCompressedAnimation::vftable` (accessor) 🔧 |
| `00dca090` | Spline destroy wrapper — calls dtor + frees memory 🔧 |
| `00dc9f30` / `00dc9f40` | Tiny vtable getters 🔧 |

### Inner ctor / fixup bodies

| FUN | Role | Status |
|---|---|---|
| `00dcc280` | Delta byte-swap pass — called by `00dc9d10` when init_flag set 💀 |
| `00dd4b00` (referenced) | Wavelet byte-swap pass | 💀 |
| **`00dd1a00`** | **Spline per-block per-track header walker** ✅ — describes dnap layout |
| `00dd1d10` | Spline encoder body (huge) — used by `00dd2a30` | 💀 |

### Format-defining helpers (the spec for dnap)

| FUN | Role | Status |
|---|---|---|
| **`00dd1810`** | Trans/Scale component dispatcher (calls `00dd1530` + `00dd1560`) | ✅ |
| **`00dd1850`** | Rotation component dispatcher (calls `00dd1530` + `00dd06a0`) | ✅ |
| **`00dd1530`** | Stream byte size calculator | ✅ |
| **`00dd1560`** | Trans/Scale per-component layout walker | ✅ |
| **`00dd06a0`** | Rotation layout walker — uses `DAT_00e71108`/`DAT_00e71120` | ✅ |
| **`00dd0680`** | Jump table dispatch: `(*PTR_LAB_00f73838[encoding_type])(cursor)` | ✅ |
| **`00dd14d0`** | Cursor advance + byte-swap helper (1/2/4 byte variants) | ✅ |
| **`00dd4680`** | Time → (block, local_time, sub_frame) converter | ✅ |
| `00dd1c60` / `00dd1890` / `00dd1ae0` / `00dd1730` / `00dd1770` / `00dd1610` | Spline encoder helpers (knot writers) | 💀 |
| `00dd2c70` | Scratch struct dtor | 🔧 |
| `00dd2f30` | Integer formatter (logging) | 🔧 |
| `00dd2dd0` / `00dd2de0` / `00dd2df0` | Spline vmethod forwarders | 💀 |
| `00dd2fe0` / `00dd3830` | Spline sample helpers — calls `00dd4680` | 💀 |
| `00dd4180` | Helper | 💀 |
| `00dd4390` / `00dd4500` | Sampler bodies | 💀 |
| `00dd3ce0` | Spline dtor — frees 5 dynamic arrays | 💀 |

### Bitstream decoders (delta path, dead)

| FUN | Role |
|---|---|
| `00dcc100` | Delta interp / scratch fill | 💀 |
| `00dcc730` / `00dcc830` | Sample cache hit/miss | 💀 |
| `00dcc6e0` / `00dcc1a0` / `00dcc1d0` | Delta vftable methods | 💀 |
| `00dcbdb0` | Time→frame helper (Delta variant) | 💀 |
| `00dcbb30` / `00dcbb40` / `00dcbcb0` / `00dcbe90` / `00dcbea0` / `00dcbeb0` | Delta vftable methods | 💀 |
| `00dcbf10` / `00dcbfc0` / `00dcc060` | Delta vftable methods | 💀 |
| `00dcca00` | Delta dtor | 💀 |
| `00dde310` | Prefix-sum (delta-decode) helper | 💀 |
| `00dde3c0` | Per-component bit-window decoder | 💀 |
| `00dddf80` | Bits-needed query | 💀 |
| `00dd6ad0` / `00dd6a30` | Bitstream front-end + per-track mask analyzer | 💀 |
| `00dd7070` | Mask analyzer (4-counter output) | 💀 |
| `00dd7b00` | Per-track recompose (the smallest3 W reconstruction) | 💀 |

### Wavelet helpers (dead)

| FUN | Role |
|---|---|
| `00dd5030` | Wavelet per-track loop | 💀 |
| `00de5910` | Wavelet inverse transform | 💀 |
| `00de6470` | Range-coded write (wavelet) | 💀 |

### Rotation encoder bodies (dead — but documented Havok formats)

| FUN | Role |
|---|---|
| `00dd1530` | Per-encoding-type cursor advance | 🔧 |
| `00de7e70` / `00de7fd0` | Spline-related helpers | 💀 |
| `00de8b10` | Same | 💀 |
| `00de42a0` | Encoder helper | 💀 |
| `00de17a0` / `00de1a90` / `00de1c30` / `00de1cf0` / `00de0c50` | Encoder utility chain | 💀 |
| `00de67d0` | Library init helper | 🔧 |
| `00ddf700` | High-level init | 🔧 |

---

## §3 Format-defining DATA tables (all critical)

| DAT | Role |
|---|---|
| **`00e71108`** | **Alignment table** for rotation encoding types (6 entries: `[4,1,2,1,2,4]`) ✅ |
| **`00e71120`** | **Byte-size table** for rotation encoding types (6 entries: `[4,5,6,3,2,16]`) ✅ |
| `00e74cb0` | `AnimCompressionParams` struct — global compression settings | 📋 |
| `00e9dd30` | String pool entry: `"AnimFilename:RsRef<AnimResource>"` | 📋 |
| `01009ae8` | Allocator failure callback function pointer | 🔧 |

---

## §4 Resource manager (live — handles all asset loading)

| FUN | Role | Status |
|---|---|---|
| **`00450760`** | `RsMgr::AcquireOrLoad` — generic resource acquire entry. **60+ callers** | ✅ |
| **`00451000`** | `RsMgr::Lookup` — manager lookup with type/hash | ✅ |
| `00451330` | Resource init helper — calls vmethod[0x34] for type-specific load | ✅ |
| `0066a540` | `AnimResourceRsMgr::vftable[14]` — `return 0xFF;` (no-op stub) | ⚙️ |
| `00d51460` | `AnimResourceRsMgr::vftable[15]/[16]` — empty `return;` (no-op stub) | ⚙️ |

---

## §5 CoSkeleton runtime (live)

| FUN | Role |
|---|---|
| `00a89a00` | `CoSkeleton::operator new` (allocates 0xa0 bytes) ✅ |
| `00a89a50` | CoSkeleton class registration 📋 |
| `00a89af0` | `CoSkeleton::ctor` (initializes state) ✅ |
| `00a89bf0` | `CoSkeleton::dtor` ✅ |
| `00a89f50` | `CoSkeleton::lazyInit` — allocates 0x290-byte bone math buffer ✅ |
| `00a89700` | Registers `kAP_*` animation priority enum (26 entries) 📋 |
| `00a8a4b0` / `00a8a4f0` | `CoSkeleton::setStateMachine` / `clearStateMachine` ✅ |
| `00a8a530` | `CoSkeleton::onParentChange` (re-resolves parent transform) ✅ |
| `00a8a580` | `CoSkeleton::release` (destructs child + frees state) ✅ |
| `00a8b230` | TaskInstance ctor for CoSkeleton thread task ✅ |
| `00a8b770` | Thread-task body — bone update tick (called by worker pool) ✅ |

---

## §6 Animation track sampling / blending (live runtime, but high-level)

| FUN | Role |
|---|---|
| `0065ad10` | **Animation track sampling driver** — iterates tracks, dispatches | ✅ |
| `0065b260` | Stance-aware sampling variant | ✅ |
| `0065ba90` | Per-track applicator — writes transforms onto skeleton | ✅ |
| `00433130` | SIMD 4-quat normalization loop | ✅ |
| `00433d80` | Multi-track quat SLERP blend | ✅ |
| `00436c70` | Bone matrix multiply + weight | ✅ |
| `0043bba0` | Iterator helper (calls vtable visitors) | ✅ |
| `00499f70` | Per-bone helper used in sampling | ✅ |
| `00ade360` | Larger animation-related routine | ✅ |

---

## §7 Schema/property setup (compile-time, defines text formats)

These functions register attributes on game classes — they tell the
engine "this struct has fields X, Y, Z with types A, B, C". The
attributes describe `.Stance`, `.ComboPose`, `.ComboAnim`,
`CcActorPlayAnim`, etc. text-format property files.

| FUN | What it sets up |
|---|---|
| `0040ea40` | `AnimCompressionParams` 📋 |
| `00541e10` | `AnimEvent_Footstep` 📋 |
| `005fbac0_005fbac0` | `CcActorPlayAnim` (cutscene play-anim command) — Animation:RsRef<AnimResource>, ShouldLoop, EaseIn/Out, etc. 📋 |
| `00644490` | Dialogue line attributes — Line, SoundCueName, BodyAnim, BodyAnimJoint 📋 |
| `00906c30` | Locomotion — MinSpeed, MovementBlendInTime, GroundSpeeds 📋 |
| `0090b860` | Head/eye/idle config — HeadJoint, EyeBlinkAnim 📋 |
| `00916350` | **Master Stance schema** — all the *Anims arrays (Forward/Backward/Turn/Stop/Idle/Death/etc.) 📋 |
| `0094ac90` | IdleAnimation properties 📋 |
| `0095cb10` | Mount/attachment properties 📋 |
| `00a11f30` | Wheel/suspension physics constraints 📋 |
| `00a38440` | UnitOrder state machine (Attack, Follow, Defend) 📋 |
| `00a92360` | Leg-IK config 📋 |
| `004ba320` | Component vftable cache 📋 |
| `004baaa0` | Component-tree dtor (mirror of above) 📋 |
| `009e1b40` | `CoRatMount::Idle` registration 📋 |
| `00a15c70` | Generic registration 📋 |

---

## §8 Attribute reader infrastructure (live, generic)

| FUN | Role |
|---|---|
| `004411e0` | Attribute lookup by name |
| `00441360` / `00441400` / `00441480` / `004414e0` | Misc attribute helpers |
| `00441630` | String hashing |
| `00441750` / `00441880` / `004418e0` / `00441980` | Misc attribute helpers |
| `006b40a0` | Generic RTTI message-buffer push helper |
| `009186b0` / `009186b8` | Vmethod wrappers |
| `00918900` | Enum-attribute reader (text format) |
| `00918c30` | List-attribute reader |
| `00918d60` | Reference-attribute reader |
| `00919710` | Array-iterator helper |
| `00919fa0` / `0091a000` | Property reader helpers |
| `00915c70` / `009161e0` | Property-table init |

---

## §9 AnimResource consumers (live, but use already-loaded data)

These functions **look up** an AnimResource via the resource manager
but don't decode the dnap bytes themselves — they read already-cached
runtime state.

| FUN | Role |
|---|---|
| `00764C40` | Property getter (animation reference) |
| `008488f0` | `PlayAnimAction`-related |
| `008f6f10` | `PlayAnimAction::computeMinMaxTime` |
| `008f7560` | Helper |
| `008fae70` / `008fdf10` | More PlayAnim helpers |
| `00a9a980` / `00a9a9e0` / `00a9aa90` / `00a9aae0` / `00a9be30` | State queries on loaded animations |
| `0063ffe0` | Property hook |
| `0048a4b0` | Top-level boot sequencer (init kAP_* + sub-systems) |

---

## §10 Specific UI / particle / mesh resource handlers (unrelated)

These are present because we accidentally exported their resource manager
helpers when chasing the resource manager. They handle other resource types.

| FUN | Resource type | Role |
|---|---|---|
| `005c4b00` / `005c4ed0` / `005c5700` | `Effect` | Particle/effect lookups ⚙️ |
| `00468c80` / `00468b30` / `00470ac0` / `0046a540` | `DUIMovie` | UI movie playback ⚙️ |
| `00577570` / `00578ef0` | `PhysicsRigidBody` | Physics constraint queries ⚙️ |
| `00589030` | Generic ⚙️ |
| `004f2a10` | Effect helper ⚙️ |
| `00402950` / `00402e40` | UI/audio init ⚙️ |
| `0048a540` | Larger init ⚙️ |
| `0042a0d0` / `0042a3b0` | Misc ⚙️ |
| `0043f1d0` | `PoseAnimation` ctor (different from sampling) ⚙️ |
| `0045fe10` / `0045fee0` | Misc ⚙️ |
| `006a8a30` | Task/job ⚙️ |

---

## §11 Memory / string utility helpers

| FUN | Role |
|---|---|
| `00404880` | Various small helpers |
| `00c8da60` | TLS pool free |
| `00c8dae0` | Memory helper |
| `00c8e490` / `00c8e690` | Memory helpers |
| `00c8e760` / `00c8e770` | Inherited `hkBaseObject` methods (vtable slots [1]/[2]) |
| `00c8ece0` | Dynamic-array growth |
| `00c8f330` / `00c8f8d0` | More memory routines |
| `00c903a0` | Memory helper |
| `00c98290` / `00c98730` | std::ostream-style formatters (logging) |
| `00c994a0` / `00c99a50` | Logging helpers |
| `00fd7d0` | Helper |

---

## §12 Havok packfile / RTTI infrastructure (mostly dead code)

The 0xcad000–0xcc0000 range contains Havok's **packfile reader/writer**
and **RTTI infrastructure**. These are dead-code Havok SDK boilerplate
that ships with BL.exe but isn't called for dnap files (dnap uses a
custom magic, doesn't go through the standard packfile reader).

| FUN address range | Role |
|---|---|
| `00cad230` / `00cad470` / `00cad5a0` / `00cad7b0` / `00cadff0` | Havok class machinery 💀 |
| `00cae1e0` | References `PackfileObjectsCollector::vftable` 💀 |
| `00cae800` / `00caea00` / `00caeb90` / `00caedf0` / `00caeea0` | Same 💀 |
| `00caf450` / `00caf710` / `00caf9c0` | `hkPackfileObjectUpdateTracker::vftable` setters 💀 |
| `00caff10` / `00caff80` | `hkBinaryPackfileWriter::vftable` setters 💀 |
| `00cb0040` through `00cb6850` (~25 funcs) | Havok serializer / RTTI / streamwriter 💀 |
| `00cb6ed0` | Packfile object tracker 💀 |
| `00cb8240` / `00cb84d0` | Havok RTTI 💀 |
| `00cb9780` | More serializer 💀 |
| `00cb9ab0` / `00cb9e90` | XML packfile reader 💀 |
| `00cb9f80` | `hkXmlPackfileReader.cpp` body — large XML parser 💀 |
| `00cbae90` / `00cbc120` / `00cbc250` / `00cbc4c0` / `00cbcc30` / `00cbd5d0` / `00cbd760` | Packfile writer helpers 💀 |
| `00cc3c70` / `00cc67d0` / `00cc7a00` | More packfile machinery 💀 |
| `00ccf9a0` | Helper 💀 |
| `00cd1dc0` / `00cd2240` / `00cd2b10` / `00cd5090` / `00cdc1d0` / `00ce4790` / `00ce9f40` / `00cfb1e0` / `00d33b80` | Havok serialization helpers 💀 |
| `00d7c830` / `00d7e230` / `00d7fb20` / `00d7fcf0` / `00d800b0` | Havok class init / RTTI 💀 |

---

## §13 AF range — additional Havok class functions

This 0xaf range contains many small Havok class methods (vtable
methods, getters, setters). All inherited from Havok library code.

| FUN | Notes |
|---|---|
| `00af40b0` through `00af50e0` (~18 funcs) | Havok base class vtable methods, mostly small forwarders ⚙️ |
| `00abec40` / `00ab6ac0` | Havok utility ⚙️ |
| `00bf4ff0` | Generic helper ⚙️ |

---

## §14 thunk_

| File | Role |
|---|---|
| `thunk_FUN_00cb33b0` | Compiler-generated thunk wrapping `FUN_00cb33b0` (vtable adjustor for multiple inheritance) |

---

## §15 Decompilation/UI/Game data (DAT_ files)

| DAT | Role |
|---|---|
| `00e71108` | **Spline rotation alignment table** (6 × u32: `[4,1,2,1,2,4]`) ✅ |
| `00e71120` | **Spline rotation byte-size table** (6 × u32: `[4,5,6,3,2,16]`) ✅ |
| `00e74cb0` | `AnimCompressionParams` struct |
| `00e9dd30` | String: `"AnimFilename:RsRef<AnimResource>"` |
| `01009ae8` | Function pointer (allocator failure callback) |

---

## What everyone normally needs to read

If you only read 5 things from this folder:

1. **[`HANDOFF.md`](HANDOFF.md)** — practical "what do I do" guide
2. **[`ANIMATION_FUN_ANALYSIS.md`](ANIMATION_FUN_ANALYSIS.md) §19** — the dnap format spec
3. **[`b20_horse_anim_parser.py`](b20_horse_anim_parser.py)** — working structural parser
4. **[`dnap_spline_decoder.py`](dnap_spline_decoder.py)** — quaternion decoders
5. **[`blender_dnap_animator.py`](blender_dnap_animator.py)** — Blender import script

The format-spec functions in §2 are what `dnap_spline_decoder.py`
implements in Python. Everything in §1, §10, §12, §13 is either dead
code or unrelated game subsystems — they're in the export folder
because we exported them while figuring out which functions WERE
relevant. They have negative value for finishing the dnap project but
positive value as a reference for anyone looking at adjacent BL
subsystems (UI, particles, physics).

## What's still genuinely missing

Per [HANDOFF.md](HANDOFF.md):
- B-spline interpolation between control points (documented Havok algorithm)
- Empirical pin-down of the per-track header base offset across all 27 animations

These are coding tasks, not RE — see `HANDOFF.md` for the path forward.
