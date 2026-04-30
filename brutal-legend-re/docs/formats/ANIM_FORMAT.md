# Animation/Skeleton Format

**Status:** In Progress
**Game:** Brutal Legend
**Engine:** Buddha (Double Fine)
**Updated:** 04-25-26

---

## Overview

Animation and skeleton data in Brutal Legend is stored within DFPF V5 containers, similar to models. The game uses a combo-based animation system.

## Animation Asset Types

| Type | Ver | Description |
|------|-----|-------------|
| .ComboAnim | 0 | Combo attack animations |
| .ComboPose | 1 | Combat pose data |
| .Stance | 3 | Idle/stance poses |
| .AnimMap | 1 | Animation mapping/listing |
| .AnimResource | ? | Animation Data |
| .AnimResource.header | ? | Animation data header |

## Animation System

### ComboAnim (Version 0)

Combo animations define attack sequences:

`
characters/bipeds/a01_avatar/animations/
+-- action_charge_focus:ComboAnim
+-- action_combo_focused_c:ComboAnim
+-- action_combosolo_elecbomb1-5:ComboAnim
+-- action_dodge_backward:ComboAnim
+-- action_dodge_forward:ComboAnim
+-- action_melee_back_a:ComboAnim
+-- action_melee_combo_a_1-4:ComboAnim
+-- boost_melee_axedash:ComboAnim
+-- boost_melee_powerslide:ComboAnim
`

### Stance (Version 3)

Stance data defines character poses:

`
a01_avatar/
+-- relaxed:Stance           # Idle stance
+-- block:Stance             # Blocking pose
+-- boost:Stance             # Boosting pose
+-- drive_a00:Stance         # Driving pose (The Deuce)
+-- deployed_a00:Stance      # Deployed from vehicle
+-- falling:Stance           # Falling pose
`

### ComboPose (Version 1)

Combat pose data for branching combos:

`
a01_avatar/
+-- brancha:ComboPose
+-- branchaa:ComboPose
+-- branchaaa:ComboPose
+-- branchidle:ComboPose
+-- postboost:ComboPose
+-- powerslide:ComboPose
`

## Animation Asset Sizes

Typical animation data sizes (from manifest):

| Asset | Disk Size | Installed Size |
|-------|-----------|----------------|
| ComboAnim | 0-1 KB | 0-1 KB |
| Stance | 1-3 KB | 1-3 KB |
| ComboPose | 0-6 KB | 4-6 KB |
| AnimResource | 0-16 KB (note this is me just guessing)  | 

## Skeleton/Rig Format

### Rig Assets

Skeleton data is stored as MeshSet assets in the 
ig/ subfolder:

`
characters/bipeds/a01_avatar/rig/
+-- a01_avatar:MeshSet           # Main skeleton rig
+-- accessories/silenceheadwrap   # Accessory rigs
+-- accessories/variationb_longsleeves
+-- props/a01_handkerchief
+-- stumps/lf_leg, rt_leg, neck1
`

### Rig Sizes

| Asset | Size |
|-------|------|
| Main rig (a01_avatar) | ~5 KB |
| Accessory rigs | 1-2 KB |
| Stump meshes | 1 KB |

## Bundle Location

Animation assets are stored in **Man_Trivial.~h/.~p**:

- Header: 716,990 bytes
- Data: 13,631,488 bytes
- 10,249 total assets including animations

## Extraction

Animations are extracted along with other DFPF assets using:
1. DoubleFine Explorer (bgbennyboy)
2. Custom DFPF V5 parser
3. Bit-field decoding per DFPF_ANALYSIS.md

## Reverse Engineering: Animation Pipeline

The following functions were identified via Ghidra analysis of `BrutalLegend.exe` and memory dumps. They represent the flow from high-level game logic down to low-level Havok math and vertex skinning.

### 1. Game Logic Layer (`CoSkeleton`)
*Brutal Legend's custom wrapper around Havok objects.*

| Address | Function Name | Role | Description |
| :--- | :--- | :--- | :--- |
| `0x00a89af0` | `CoSkeleton::Constructor` | **Initialization** | Initializes a new skeleton instance, sets default values, and assigns the VFTABLE. |
| `0x00a89bf0` | `CoSkeleton::Destructor` | **Cleanup** | Cleans up memory and releases references when a character is removed. |
| `0x00a89f50` | `CoSkeleton::InitializeState` | **State Creation** | Allocates pose buffer memory and links it to `hkaAnimatedSkeleton`. Called on animation start. |
| `0x00a8a530` | `CoSkeleton::SyncState` | **State Sync** | Checks for state changes (e.g., Walk → Run) and updates internal caches. |
| `0x00a8a580` | `CoSkeleton::CleanupState` | **State Cleanup** | Frees pose buffers and resets pointers when an animation stops. |
| `0x00a8b230` | `CoSkeleton::CreateUpdateJob` | **Job Factory** | Creates a `TaskInstance` and assigns the worker thread function (`0x00a8b770`). |
| `0x008449a0` | `ThreadPool::SubmitTask` | **Job Signal** | Signals the thread pool that the animation job is ready for execution. |
| `0x006b40a0` | `CoSkeleton::SubmitSkinningJob` | **Job Submission** | Submits the final skinning job to the multi-threaded system to move mesh vertices. |
| `0x00a8a4b0` | `CoSkeleton::LinkComponent` | **Linking** | Links the `CoSkeleton` to other components (like Physics) in a priority-based list. |
| `0x00a8a4f0` | `CoSkeleton::UnlinkComponent` | **Unlinking** | Removes the `CoSkeleton` from the component linked list. |
| `0x00644490` | `AnimLineAttribute::Register` | **Dialogue** | Registers voice line/facial animation metadata (SoundCueName, BodyAnimJoint). |
| `0x004baaa0` | `ComponentManager::RemoveComponent` | **System** | Generic manager for removing components from an actor. |
| `0x0041aab0` | `MemoryAllocator` | **System** | Allocates (`0x0041aab0`) and Deallocates (`0x0041af50`) heap memory for skeletons. |
| `0x004426f0` | `ThreadSync` | **System** | Enters (`0x004426f0`) and Exits (`0x00442610`) critical sections to prevent race conditions. |
| `0x0043bba0` | `Havok::BlockAllocator::Alloc` | **Memory Mgmt** | Manages 64-byte block allocations for animation decompression buffers. |

### 2. The "Captain" Layer (Update Loop)
*The code that executes every frame to advance bone positions.*

| Address | Function Name | Role | Description |
| :--- | :--- | :--- | :--- |
| `0x00a8b770` | `AnimationJob::Execute` | **The Captain** | Iterates through bones/tracks, calling time-advance and sampling functions. |
| `0x00a8bdd0` | `Track::AdvanceTime` | **Time Stepper** | Updates the internal "clock" for specific animation tracks using delta time. |
| `0x00a8c110` | `Track::SamplePose` | **Pose Sampler** | Requests new bone positions from Havok at the current time; returns a "dirty" mask. |
| `0x00a8b7f0` | `AnimationJob::Cleanup` | **Job Cleanup** | Frees resources used by the animation job after execution. |
| `0x00a8c2c0` | `Job::Finalize` | **Job Finalizer** | Resets the job's vtable from `ThreadTask` to `Runnable` upon completion. |

### 3. Havok Engine Layer (Internal Math)
*Low-level compression and decomposition logic (Addresses `0x00dc...` / `0x00dd...`).*

| Address | Function Name | Role | Description |
| :--- | :--- | :--- | :--- |
| `0x00dccfb0` | `hkaDeltaCompressedAnimation::samplePartialPose` | **The Sampler** | Calculates final bone transforms for a specific moment in time. |
| `0x00dd7b00` | `Havok::DecodeBoneTransform` | **The Decoder** | Decodes compressed quaternions/floats into usable bone rotation/position data. |
| `0x00dcca40` | `Havok::DecompressDeltaChunk` | **The Engine** | Performs heavy-lifting delta-decompression and interpolation between keyframes. |
| `0x00dd51b0` | `Havok::DecompressWaveletChunk` | **Wavelet Decoder** | Handles `hkaWaveletCompressedAnimation`. Uses wavelet transforms for higher compression. |
| `0x00dd5030` | `Havok::WaveletMathCore` | **Wavelet Core** | Core mathematical operations for wavelet reconstruction. |
| `0x00dd1d10` | `Havok::DecompressSplineChunk` | **Spline Decoder** | Handles `hkaSplineCompressedAnimation`. Reconstructs bone transforms from spline curves (likely Hermite/Catmull-Rom). Includes quaternion normalization and track-specific evaluation. |
| `0x00433130` | `Math::NormalizeQuaternions` | **Math Helper** | SIMD-optimized function that normalizes a batch of quaternions. |
| `0x0040ea40` | `AnimCompressionParams::Register` | **System Init** | Registers compression settings (bit-depths, tolerances) used by Havok decoders. |

### 4. Rendering Layer (Vertex Skinning)
*Applies bone movements to the 3D model mesh.*

| Address | Function Name | Role | Description |
| :--- | :--- | :--- | :--- |
| `0x00436c70` | `Skinning::ApplyMatrices` | **The Skin** | Multiplies final bone matrices by vertex weights to transform the mesh. |
| `0x00432510` | `Skinning::BatchProcess` | **Batcher** | Processes vertices in batches for performance optimization. |
| `0x00432790` | `Skinning::Finalize` | **Finalizer** | Finalizes the skinning process for the current frame. |

### 5. Integration & Locomotion Layer
*Higher-level systems managing animation states, blending, and physics integration.*

| Address | Function/Class Name | Role | Description |
| :--- | :--- | :--- | :--- |
| `0x0090a4c0` | `CoLocomotionAnimation` | **Locomotion** | Complex locomotion system blending walk/run/strafe animations. |
| `0x009d14a0` | `CoLocomotionSimpleAnimation` | **Locomotion** | Simplified locomotion for NPCs or props. |
| `0x00913f70` | `CoConstructable::Construction_Animation` | **Building** | Handles animations for building construction/destruction. |
| `0x0099e260` | `Mount/Dismount Animation Range` | **Mounts** | Defines procedural animation windows for mounting/dismounting. |
| `0x009fa6f0` | `FiringAnimationAimingLockout` | **Combat** | Locks out aiming controls during specific phases of firing animations. |
| `0x00eaeb78` | `m_pRagdollToBindpose` | **Physics** | Maps ragdoll physics bodies back to animation bones for seamless transitions. |
| `0x00de67d0` | `Havok License Check` | **System** | Runtime validation of Havok middleware licenses. |

### 6. Specialized Systems: Foot IK & Kamikaze
*Specific subsystems identified via RTTI and string analysis.*

#### A. Foot Inverse Kinematics (Foot IK)
*Ensures character feet adhere to terrain geometry. Controlled by `BlendNode_FootIK`.*

| Address/String | Identifier | Role | Description |
| :--- | :--- | :--- | :--- |
| `0x00ed6d3c` | `LegIKs` | **Config** | Master container for leg IK settings. |
| `0x00ed92c8` | `EnableLegIK` | **Toggle** | Enables/disables leg IK for a specific stance. |
| `0x00ed6d60` | `DisableFootIK` | **Toggle** | Global override to disable foot IK calculations. |
| `0x00ed6d90` | `UseCheapFootIK` | **Optimization** | Enables cheaper raycasts for small/AI characters. |
| `0x00ed6df4` | `FootIKFootSteps` | **Audio** | Procedurally generates footstep sounds from IK data. |
| `0x00ed6e44` | `FootIKFootStepsOnly` | **Audio Only** | Generates sounds/effects but disables actual foot positioning. |
| `0x00ed6ee0` | `FootIKLODScale` | **LOD** | Scales IK precision based on screen-space size. |
| `0x00fbf9c8` | `.?AVBlendNode_FootIK@@` | **RTTI Class** | The C++ class responsible for executing the Foot IK blend. |
| `0x00ef8830` | `kAP_FootIK` | **State Tag** | Animation state/action point tag for Foot IK activation. |

---

## Data Structures & Memory Maps

### The AnimResource File Format
Brutal Legend uses a custom Double Fine wrapper (`AnimResource`) around standard Havok data. 

#### Header Structure (Offsets `0x00` - `0x40`) (may not be correct) 
| Offset | Size | Type | Description |
| :--- | :--- | :--- | :--- |
| `0x00` | 4 | ASCII | Magic Bytes: `"dnap"` |
| `0x04` | 4 | Float | Version/Scale Factor |
| `0x08` | 4 | Float | Duration (Seconds) |
| `0x0C` | 2 | UInt16 | Bone Count |
| `0x0E` | 2 | UInt16 | Track Count |
| `0x10` | 2 | UInt16 | Rotation Track Count |
| `0x12` | 2 | UInt16 | Translation Track Count |
| `0x14` | 2 | UInt16 | Compression Type (`1`=Uncompressed, `2`=Delta, `3`=Wavelet, `4`=Spline) |
| `0x18` | 4 | UInt32 | Data Offset (Start of compressed bone data) |

#### Track Map (`transformTrackToBoneIndices`)
Located immediately after the header (typically offset `0x40`). This array maps Animation Tracks to Skeleton Bone Indices.

**Array Content (UInt16 Little-Endian):**
`1, 3, 3, 5, 7, 8, 9, 9, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20...`

*Note: Track 0 maps to Bone 1 (Pelvis), Track 1 to Bone 3 (Spine1), etc.*

### Resource Management System
Brutal Legend uses a sophisticated resource manager (`AnimResourceRsMgr`) to handle animation loading and lookup.

* **Name-Based Lookup:** `HashTable<Name, RsRef<AnimResource>>` allows requesting animations by string name (e.g., `"relaxed_trot"`).
* **Rig-Based Lookup:** `HashTable<RsWeakRef<Rig>, RsRef<AnimResource>>` ensures animations are only played on compatible skeletons.
* **Reference Counting:** Uses `RsRef` (strong) and `RsWeakRef` (weak) to manage memory lifecycle and prevent leaks.
* **Combo Trees:** Stored as `Array<Tuple<Float, RsRef<AnimResource>, Bool>>` where Float is blend weight/timing, RsRef is the animation, and Bool is a flag (e.g., `IsLooping`).

### Class Hierarchy (RTTI)
Confirmed via RTTI strings in the executable:

#### Havok Core Classes
* `hkaAnimation` (Base)
* `hkaDeltaCompressedAnimation` (Most Common)
* `hkaWaveletCompressedAnimation` (High Compression)
* `hkaSplineCompressedAnimation` (Spline-based)
* `hkaInterleavedUncompressedAnimation` (Raw Data)
* `hkaAnimationBinding` (Links Anim to Skeleton)
* `hkaAnimationContainer` (Holds multiple anims)

#### Double Fine Wrapper Classes
* `SkeletalAnimation` (Base Wrapper)
* `CompressedSkeletalAnimation`
* `UncompressedSkeletalAnimation`
* `PoseAnimation` (Static Poses)
* `CoLocomotionAnimation` (Movement Blending)
* `CoLocomotionSimpleAnimation` (Simplified Locomotion)
* `CoConstructable::Construction_Animation` (Building Anims)
* `CoKamikazeMount` (Kamikaze Unit Logic)
* `BlendNode_FootIK` (Foot IK Processing)

#### Attribute & Priority System
* `ReferenceAttribute<enum_AnimationPriority>`: Manages blending priorities (Face > Body > Root).
* `AnimationPriority`: Enum defining layer importance.

### Animation State Machine (`AnimationType`)
Defined in RTTI at `0x00eb0a98`. Controls blending and looping behavior.

| ID | Name | Behavior |
| :--- | :--- | :--- |
| `0` | `ANIMATION_None` | No active animation. |
| `1` | `ANIMATION_Looping` | Standard loop with blending (e.g., Idle, Run). |
| `2` | `ANIMATION_AlphaRamp` | Fades in/out via alpha blending (Effects/UI). |
| `3` | `ANIMATION_LoopingNoBlend` | Hard-cut looping (no blending with other layers). |

### Animation Events
Embedded triggers for gameplay effects, identified by these strings:
* `AnimEvent_PlaySound`: Triggers audio cues.
* `AnimEvent_Footstep`: Syncs footfalls with terrain.
* `AnimEvent_SpawnParticles`: Visual effects (sparks, dust).
* `AnimEvent_GoRagdoll`: Transitions to physics simulation.
* `AnimEvent_HideAttachment`: Hides weapons/items during specific poses.
---

## Challenges & Solutions

### The "Twisting" Issue
Initial attempts to play animations in blender resulted in twisted meshes.
*   **Possible Cause:** Mismatch between the game's **Bind Pose** and the importer's default pose, combined with treating **Delta-Compressed Integers** as Absolute Quaternions.
*   **Possible Solution:** 
    1. Parse the **Bind Pose Matrix** from the `.rig` file for each bone.
    2. Implement **Delta Accumulation** (summing integers over time) to get the local animated quaternion.
    3. Multiply the **Bind Pose Quaternion** by the **Animated Local Quaternion** to get the final world rotation.
    4. Skip **Track 0** if it contains Root Motion (Translation) instead of rotation.

### Key Breakthroughs
1.  Identified the `transformTrackToBoneIndices` array in memory and the file header.
2.  Distinguished between `StRecomposeD` (Delta) and `StRecomposeW` (Wavelet) compression via header flags.
3.  Located the `AnimationJob::Execute` function that drives the update loop.
4.  Mapped the full `CoSkeleton` lifecycle from creation to job submission.
5.  Identified the thread synchronization primitives (`Lock`/`Unlock`) ensuring safe multi-threaded access.
6.  Discovered the `AnimResourceRsMgr` and hash-table lookup systems for resource management.
7.  Decoded the Double Fine `AnimResource` header structure to correctly(maybe) locate data offsets.

---


## References

- DFPF_ANALYSIS.md - Container format details
- MODEL_FORMAT.md - Model/skeleton info
- ComboAnim/ComboPose/Stance - Internal type names in manifests

---

*Document generated as part of Brutal Legend reverse engineering project*
