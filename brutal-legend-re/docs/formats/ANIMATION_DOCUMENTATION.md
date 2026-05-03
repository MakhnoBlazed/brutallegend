# Brutal Legend Ghidra exports — quick reference

A flat reference of every `FUN_*.txt`, `DAT_*.txt`, and `thunk_*.txt`
file in this folder. One line per item, organized by subsystem.

For deep technical analysis see [`ANIMATION_FUN_ANALYSIS.md`](ANIMATION_FUN_ANALYSIS.md).
For practical use see the parser scripts and `dnap_spline_decoder.py`.

**Status legend:**
- ✅ live & relevant to dnap animation
- 🔧 utility, used by animation code
- 💀 dead code (Havok SDK boilerplate, never called by BL at runtime)
- 📋 schema / class registration (init-time only)
- ⚙️ unrelated game subsystem (Effect, DUIMovie, Physics, UI, etc.)

**Address-range cheat sheet:**
- `0x00400000–0x00500000` — early game systems, attribute schemas
- `0x00500000–0x009f0000` — main game logic
- `0x00a30000–0x00d80000` — game / Havok runtime mix
- `0x00cad000–0x00cbf000` — Havok RTTI / packfile machinery (mostly dead)
- `0x00dc0000–0x00de9000` — Havok animation runtime (mostly dead, but encodes the dnap format)
- `0x00e1b000–0x00e1c000` — class registration functions

---

## §1 Decompression core

| FUN | Role | Status |
|---|---|---|
| `00a66470_00a66470` | **zlib `inflate()`** state machine — handles all gzip/deflate | ✅ |
| `00a66470_00a66e12` | byte-identical alias of above | ✅ |
| `00a69d00_00a69d00` | **zlib `inflate_table()`** — Huffman table builder | ✅ |
| `00dcca40` | `StDecompressD` — Havok delta sampler. Unused by BL | 💀 |
| `00dccfb0` | `StDecompressDChunk` — chunk variant | 💀 |
| `00dd51b0` | `StDecompressW` — Wavelet sampler | 💀 |
| `00dd59a0` | Wavelet vftable[4] | 💀 |

---

## §2 Spline-compressed animation format (the dnap format spec)

These functions describe the on-disk format. They're "dead" (registered
but never called) but their **bodies are correct format documentation**.

### Class registration (init-time only)

| FUN | Role |
|---|---|
| `00e1b630` | Registers `hkaDeltaCompressedAnimation` 📋 |
| `00e1b7f0` | Registers `hkaSplineCompressedAnimation` 📋 |
| `00e1b750` | Registers `hkaSplineCompressedAnimationTrackCompressionParams` 📋 |
| `00e1b700` | Registers another animation-param class 📋 |
| `00e1baa0` | Registers `hkaFootstepAnalysisInfoContainer` 📋 |
| `00e1bbc0` | Registers more animation params 📋 |
| `00e1bc60` | Registers `hkaAnimation` base class 📋 |
| `00e1c340` | Registers another anim type 📋 |
| `00e16210` | Registers `hkxSparselyAnimatedStringStringType` 📋 |

### Outer ctors (set vtable, dispatch to inner)

| FUN | Class |
|---|---|
| `00dc9d10` | `hkaDeltaCompressedAnimation::ctor` → calls `00dcc280` 💀 |
| `00dca060` (in `00dcca060.txt`) | `hkaSplineCompressedAnimation::ctor` → calls `00dd1a00` 💀 |
| `00dd2a30` / `00dd2bd0` | Spline encoder ctor → calls `00dd1d10` 💀 |

### Vtable accessors / destroy wrappers

| FUN | Role |
|---|---|
| `00dc9cf0` | Destroy wrapper for Delta 🔧 |
| `00dc9d40` | Delta vmethod[12] forwarder 💀 |
| `00dc9d60` | Delta vmethod[13] 💀 |
| `00dc9d90` | small Delta helper 💀 |
| `00dca080` | Returns `hkaSplineCompressedAnimation::vftable` 🔧 |
| `00dca090` | Spline destroy wrapper 🔧 |
| `00dc9f30` / `00dc9f40` | Tiny vtable getters 🔧 |

### Inner ctor / fixup bodies

| FUN | Role | Status |
|---|---|---|
| `00dcc280` | Delta byte-swap pass | 💀 |
| **`00dd1a00`** | **Spline per-block per-track header walker** — defines dnap layout | ✅ |
| `00dd1d10` | Spline encoder body (huge) | 💀 |

### Format-defining helpers (the spec for dnap)

| FUN | Role | Status |
|---|---|---|
| **`00dd1810`** | T/S component dispatcher | ✅ |
| **`00dd1850`** | R component dispatcher | ✅ |
| **`00dd1530`** | Stream byte-size calculator | ✅ |
| **`00dd1560`** | T/S per-component layout walker | ✅ |
| **`00dd06a0`** | R layout walker — uses `DAT_00e71108`/`DAT_00e71120` | ✅ |
| **`00dd0680`** | Jump table dispatch (calls one of 6 R decoders) | ✅ |
| **`00dd14d0`** | Cursor advance + byte-swap helper (1/2/4 byte) | ✅ |
| **`00dd4680`** | Time → (block, local_t, sub_frame) converter | ✅ |
| `00dd1c60` / `00dd1890` / `00dd1ae0` / `00dd1730` / `00dd1770` / `00dd1610` | Spline encoder helpers | 💀 |
| `00dd2c70` | Scratch struct dtor | 🔧 |
| `00dd2f30` | Integer formatter (logging) | 🔧 |
| `00dd2dd0` / `00dd2de0` / `00dd2df0` | Spline vmethod forwarders | 💀 |
| `00dd2fe0` / `00dd3830` | Spline sample helpers | 💀 |
| `00dd4180` / `00dd4390` / `00dd4500` | Sampler bodies | 💀 |
| `00dd3ce0` | Spline dtor | 💀 |

### Bitstream decoders (delta path, dead)

| FUN | Role |
|---|---|
| `00dcc100` | Delta interp / scratch fill 💀 |
| `00dcc730` / `00dcc830` | Sample cache hit/miss 💀 |
| `00dcc6e0` / `00dcc1a0` / `00dcc1d0` | Delta vftable methods 💀 |
| `00dcbdb0` | Time→frame helper (Delta) 💀 |
| `00dcbb30` / `00dcbb40` / `00dcbcb0` / `00dcbe90` / `00dcbea0` / `00dcbeb0` | Delta vftable methods 💀 |
| `00dcbf10` / `00dcbfc0` / `00dcc060` | Delta vftable methods 💀 |
| `00dcca00` | Delta dtor 💀 |
| `00dde310` | Prefix-sum (delta-decode) helper 💀 |
| `00dde3c0` | Per-component bit-window decoder 💀 |
| `00dddf80` | Bits-needed query 💀 |
| `00dd6ad0` / `00dd6a30` | Bitstream front-end + mask analyzer 💀 |
| `00dd7070` | Mask analyzer 💀 |
| `00dd7b00` | Per-track recompose 💀 |

### Wavelet helpers (dead)

| FUN | Role |
|---|---|
| `00dd5030` | Wavelet per-track loop 💀 |
| `00de5910` | Wavelet inverse transform 💀 |
| `00de6470` | Range-coded write (wavelet) 💀 |

### Encoder utility chain

| FUN | Role |
|---|---|
| `00de7e70` / `00de7fd0` | Spline-related helpers 💀 |
| `00de8b10` | Same 💀 |
| `00de42a0` | Encoder helper 💀 |
| `00de17a0` / `00de1a90` / `00de1c30` / `00de1cf0` / `00de0c50` | Encoder utility chain 💀 |
| `00de67d0` | Library init helper 🔧 |
| `00ddf700` | High-level init 🔧 |

---

## §3 DATA tables

| DAT | Role |
|---|---|
| **`00e71108`** | **Alignment table** for rotation encodings (6 × u32: `[4,1,2,1,2,4]`) ✅ |
| **`00e71120`** | **Byte-size table** for rotation encodings (6 × u32: `[4,5,6,3,2,16]`) ✅ |
| `00e74cb0` | `AnimCompressionParams` struct 📋 |
| `00e9dd30` | String pool: `"AnimFilename:RsRef<AnimResource>"` 📋 |
| `01009ae8` | Allocator failure callback 🔧 |

---

## §4 Resource manager (live)

| FUN | Role |
|---|---|
| **`00450760`** | `RsMgr::AcquireOrLoad` — generic resource entry. 60+ callers ✅ |
| **`00451000`** | `RsMgr::Lookup` — manager lookup ✅ |
| `00451330` | Resource init helper ✅ |
| `0066a540` | `AnimResourceRsMgr::vftable[14]` — `return 0xFF;` (no-op) ⚙️ |
| `00d51460` | `AnimResourceRsMgr::vftable[15]/[16]` — empty `return;` ⚙️ |

---

## §5 CoSkeleton runtime (live)

| FUN | Role |
|---|---|
| `00a89a00` | `CoSkeleton::operator new` ✅ |
| `00a89a50` | CoSkeleton class registration 📋 |
| `00a89af0` | `CoSkeleton::ctor` ✅ |
| `00a89bf0` | `CoSkeleton::dtor` ✅ |
| `00a89f50` | `CoSkeleton::lazyInit` ✅ |
| `00a89700` | Registers `kAP_*` priority enum (26 entries) 📋 |
| `00a8a4b0` / `00a8a4f0` | `CoSkeleton::set/clearStateMachine` ✅ |
| `00a8a530` | `CoSkeleton::onParentChange` ✅ |
| `00a8a580` | `CoSkeleton::release` ✅ |
| `00a8b230` | TaskInstance ctor for CoSkeleton thread task ✅ |
| `00a8b770` | Thread-task body — bone update tick ✅ |

---

## §6 Animation track sampling / blending (live runtime)

| FUN | Role |
|---|---|
| `0065ad10` | Animation track sampling driver ✅ |
| `0065b260` | Stance-aware sampling variant ✅ |
| `0065ba90` | Per-track applicator ✅ |
| `00433130` | SIMD 4-quat normalization ✅ |
| `00433d80` | Multi-track quat SLERP blend ✅ |
| `00436c70` | Bone matrix multiply + weight ✅ |
| `0043bba0` | Iterator helper ✅ |
| `00499f70` | Per-bone sampling helper ✅ |
| `00ade360` | Larger animation routine ✅ |

---

## §7 Schema / property setup (compile-time)

| FUN | What it sets up |
|---|---|
| `0040ea40` | `AnimCompressionParams` 📋 |
| `00541e10` | `AnimEvent_Footstep` 📋 |
| `005fbac0_005fbac0` / `005fbac0` | `CcActorPlayAnim` (cutscene play-anim) 📋 |
| `00644490` | Dialogue line attributes 📋 |
| `00906c30` | Locomotion attributes 📋 |
| `0090b860` | Head/eye/idle config 📋 |
| `00916350` | **Master Stance schema** 📋 |
| `0094ac90` | IdleAnimation properties 📋 |
| `0095cb10` | Mount/attachment properties 📋 |
| `00a11f30` | Wheel/suspension constraints 📋 |
| `00a38440` | UnitOrder state machine 📋 |
| `00a92360` | Leg-IK config 📋 |
| `004ba320` | Component vftable cache 📋 |
| `004baaa0` | Component-tree dtor 📋 |
| `009e1b40` | `CoRatMount::Idle` 📋 |
| `00a15c70` | Generic registration 📋 |

---

## §8 Attribute reader infrastructure (live, generic)

| FUN | Role |
|---|---|
| `004411e0` | Attribute lookup by name |
| `00441360` / `00441400` / `00441480` / `004414e0` | Attribute helpers |
| `00441630` | String hashing |
| `00441750` / `00441880` / `004418e0` / `00441980` | Attribute helpers |
| `006b40a0` | RTTI message-buffer push |
| `009186b0` / `009186b8` | Vmethod wrappers |
| `00918900` | Enum-attribute reader |
| `00918c30` | List-attribute reader |
| `00918d60` | Reference-attribute reader |
| `00919710` | Array-iterator helper |
| `00919fa0` / `0091a000` | Property reader helpers |
| `00915c70` / `009161e0` | Property-table init |

---

## §9 AnimResource consumers (use already-loaded data)

| FUN | Role |
|---|---|
| `00764C40` | Property getter (anim ref) |
| `008488f0` | `PlayAnimAction`-related |
| `008f6f10` | `PlayAnimAction::computeMinMaxTime` |
| `008f7560` | Helper |
| `008fae70` / `008fdf10` | More PlayAnim helpers |
| `00a9a980` / `00a9a9e0` / `00a9aa90` / `00a9aae0` / `00a9be30` | State queries |
| `0063ffe0` | Property hook |
| `0048a4b0` | Top-level boot sequencer |

---

## §10 Unrelated game subsystems

| FUN | Resource type |
|---|---|
| `005c4b00` / `005c4ed0` / `005c5700` | `Effect` (particles) ⚙️ |
| `00468c80` / `00468b30` / `00470ac0` / `0046a540` | `DUIMovie` (UI movies) ⚙️ |
| `00577570` / `00578ef0` | `PhysicsRigidBody` ⚙️ |
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
| `00c8e760` / `00c8e770` | Inherited `hkBaseObject` methods |
| `00c8ece0` | Dynamic-array growth |
| `00c8f330` / `00c8f8d0` | More memory routines |
| `00c903a0` | Memory helper |
| `00c98290` / `00c98730` | Logging formatters |
| `00c994a0` / `00c99a50` | Logging helpers |
| `00fd7d0` | Helper |

---

## §12 Havok packfile / RTTI infrastructure (mostly dead)

| FUN address range | Role |
|---|---|
| `00cad230` / `00cad470` / `00cad5a0` / `00cad7b0` / `00cadff0` | Havok class machinery 💀 |
| `00cae1e0` | `PackfileObjectsCollector::vftable` ref 💀 |
| `00cae800` / `00caea00` / `00caeb90` / `00caedf0` / `00caeea0` | Same 💀 |
| `00caf450` / `00caf710` / `00caf9c0` | `hkPackfileObjectUpdateTracker` 💀 |
| `00caff10` / `00caff80` | `hkBinaryPackfileWriter` 💀 |
| `00cb0040` ... `00cb6850` (~25) | Havok serializer / RTTI 💀 |
| `00cb6ed0` | Packfile object tracker 💀 |
| `00cb8240` / `00cb84d0` | Havok RTTI 💀 |
| `00cb9780` | More serializer 💀 |
| `00cb9ab0` / `00cb9e90` | XML packfile reader 💀 |
| `00cb9f80` | `hkXmlPackfileReader.cpp` body 💀 |
| `00cbae90` / `00cbc120` / `00cbc250` / `00cbc4c0` / `00cbcc30` / `00cbd5d0` / `00cbd760` | Packfile writer helpers 💀 |
| `00cc3c70` / `00cc67d0` / `00cc7a00` | Packfile machinery 💀 |
| `00ccf9a0` | Helper 💀 |
| `00cd1dc0` / `00cd2240` / `00cd2b10` / `00cd5090` / `00cdc1d0` / `00ce4790` / `00ce9f40` / `00cfb1e0` / `00d33b80` | Havok serialization 💀 |
| `00d7c830` / `00d7e230` / `00d7fb20` / `00d7fcf0` / `00d800b0` | Havok class init 💀 |

---

## §13 0xaf range — additional Havok class methods

| FUN | Notes |
|---|---|
| `00af40b0` ... `00af50e0` (~18) | Havok base-class vtable methods ⚙️ |
| `00abec40` / `00ab6ac0` | Havok utility ⚙️ |
| `00bf4ff0` | Generic helper ⚙️ |

---

## §14 thunk_

| File | Role |
|---|---|
| `thunk_FUN_00cb33b0` | Compiler vtable adjustor thunk |

---

## §15 NEW: physics keyframes / camera / cutscene system (NOT animation)

These were exported in a "find keyframe-related code" pass but cover
**physics body keyframes**, **camera waypoints**, and the
**Flash/SWF cutscene system** — they DON'T decode dnap animation.

### Physics keyframes (scripted rigid-body motion)

| FUN | Role |
|---|---|
| `00e170d0` | Registers `hkpKeyframedRigidMotion` ⚙️ |
| `00d76600` | "Keyframed Rigid Bodies" string ⚙️ |
| `00577fb0` | Registers `Keyframed` motion type ⚙️ |
| `00e0f1f0` | `SetKeyframed` entity command ⚙️ |
| `0097df00` | `CoControllerKeyframe` component ⚙️ |
| `0097d830` | `KeyframedEntityImpeded` event ⚙️ |
| `0097d730` | `KeyframesCompletedMessage` event ⚙️ |
| `00e112f0` | `SetKeyframeImpedingEntity` command ⚙️ |
| `00e11330` | `SetKeyframeSpeedScale` command ⚙️ |
| `00e11370` | `IsKeyframeEntImpeded` query ⚙️ |
| `0097e110` | `KeyframeData` attribute ⚙️ |
| `009653a0` | `UseKeyframes` boolean ⚙️ |

### Camera path / cutscene cameras

| FUN | Role |
|---|---|
| `006127e0` | Camera path attributes ⚙️ |
| `0061cd20` | "Camera Shake" command ⚙️ |
| `00623890` | "Play Flash Movie" command ⚙️ |
| `0063a160` | Frame/Clump attributes ⚙️ |

### Flash / SWF cutscene rendering

| FUN | Role |
|---|---|
| `00ac3ed0` | SWF frame-rate logger / loader ⚙️ |
| `00adb860` | SWF action / DoActionLoader ⚙️ |
| `00aeb7c0` | SWF sprite frame loader ⚙️ |
| `00af8f70` | SWF helper ⚙️ |

### Havok motion (related but NOT bone keyframes)

| FUN | Role |
|---|---|
| `00dca840` | `hkaDefaultAnimatedReferenceFrame.cpp` — root motion 💀 |
| `00e1bd30` | `hkaKeyFrameHierarchyUtility` registration 💀 |
| `00e15170` / `00e151b0` | `hkMonitorStreamStringMap` 💀 |
| `00e15280` | `hkReferencedObject` base 💀 |
| `00e152b0` / `00e152e0` / `00e15310` / `00e15340` | Havok base class regs 💀 |
| `00e16050` | `hkxMeshSection` 💀 |
| `00e179f0` | Havok class reg 💀 |
| `00e18940` / `00e18950` / `00e18a30` | More Havok regs 💀 |
| `00e1b570` / `00e1b6c0` / `00e1b7b0` / `00e1bb30` / `00e1bb60` / `00e1bc20` / `00e1bd00` | Animation class regs 📋 |

### Misc unrelated exports

| FUN | Role |
|---|---|
| `00a46b00` | "Gib Joint" command ⚙️ |
| `00bc1f10` | OpenGL extension query ⚙️ |
| `00df2380` | "LockSimToFramerate" ⚙️ |
| `00df23c0` | Sim-rate helper ⚙️ |
| `00df55e0` | "KillCurrentFrame" ⚙️ |
| `00e039b0` | "ToggleFrameReplacement" ⚙️ |
| `0040d050` | UI bool/int attributes ⚙️ |
| `0043f550` | Window flags (-width/-height/-fullscreen) ⚙️ |
| `005e8960` | Sleep/wait command ⚙️ |
| `0080e090` | "OpenCollision"/"ClosedCollision" attrs ⚙️ |
| `0089a190` | Timing system attrs ⚙️ |
| `006f7270` | Generic helper ⚙️ |
| `00cda9f0` / `00cd6500` | Helpers ⚙️ |
| `00a40aa0` | Game system helper ⚙️ |
| `0096c110` | Boulder physics ⚙️ |
| `00dc9260` | Havok class init ⚙️ |

---

## What you actually need

If you only read 5 things from this folder:

1. **[`ANIMATION_FUN_ANALYSIS.md`](ANIMATION_FUN_ANALYSIS.md)** §19 — the dnap format spec (definitive)
2. **[`b20_horse_anim_parser.py`](b20_horse_anim_parser.py)** — working structural parser
3. **[`dnap_spline_decoder.py`](dnap_spline_decoder.py)** — quaternion decoders (6 Havok formats)
4. **[`dnap_to_bvh.py`](dnap_to_bvh.py)** — BVH export (currently bind-pose only)
5. **[`blender_dnap_animator.py`](blender_dnap_animator.py)** — Blender-side animator script

## What's still genuinely missing

Per §19 of the analysis doc:

1. **Pin down exact base offset** of the per-track header table per
   animation (empirical — try sweeping all candidate offsets).
2. **Implement uniform B-spline interpolation** in Python (~50 lines,
   documented Havok algorithm).
3. **Wire the decoded values** into `blender_dnap_animator.py`.

These are coding tasks, **not RE**. No more Ghidra exports needed.
