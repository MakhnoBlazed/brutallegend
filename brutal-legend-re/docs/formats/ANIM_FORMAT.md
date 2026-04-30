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

The following functions were identified via Ghidra analysis of `BrutalLegend.exe`. They represent the flow from high-level game logic down to low-level Havok math and vertex skinning.

### 1. Game Logic Layer (`CoSkeleton`)
*Brutal Legend's custom wrapper around Havok objects.*

| Address | Function Name | Role |
| :--- | :--- | :--- |
| `0x00a89af0` | `CoSkeleton::Constructor` | Initializes a new skeleton instance, sets default values, and assigns the VFTABLE. |
| `0x00a89bf0` | `CoSkeleton::Destructor` | Cleans up memory and releases references when a character is removed. |
| `0x00a89f50` | `CoSkeleton::InitializeState` | Allocates pose buffer memory and links it to `hkaAnimatedSkeleton`. Called on animation start. |
| `0x00a8a530` | `CoSkeleton::SyncState` | Checks for state changes (e.g., Walk → Run) and updates internal caches. |
| `0x00a8a580` | `CoSkeleton::CleanupState` | Frees pose buffers and resets pointers when an animation stops. |
| `0x00a8b230` | `CoSkeleton::CreateUpdateJob` | **Job Factory.** Creates a `TaskInstance` and assigns the worker thread function (`0x00a8b770`). |
| `0x006b40a0` | `CoSkeleton::SubmitSkinningJob` | Submits the final skinning job to the multi-threaded system to move mesh vertices. |

### 2. The "Captain" Layer (Update Loop)
*The code that executes every frame to advance bone positions.*

| Address | Function Name | Role |
| :--- | :--- | :--- |
| `0x00a8b770` | `AnimationJob::Execute` | **The Captain.** Iterates through bones/tracks, calling time-advance and sampling functions. |
| `0x00a8bdd0` | `Track::AdvanceTime` | Updates the internal "clock" for specific animation tracks using delta time. |
| `0x00a8c110` | `Track::SamplePose` | Requests new bone positions from Havok at the current time; returns a "dirty" mask. |

### 3. Havok Engine Layer (Internal Math)
*Low-level compression and decomposition logic (Addresses `0x00dc...` / `0x00dd...`).*

| Address | Function Name | Role |
| :--- | :--- | :--- |
| `0x00dccfb0` | `hkaDeltaCompressedAnimation::samplePartialPose` | **The Sampler.** Calculates final bone transforms for a specific moment in time. |
| `0x00dd7b00` | `Havok::DecodeBoneTransform` | **The Decoder.** Decodes compressed quaternions/floats into usable bone rotation/position data. |
| `0x00dcca40` | `Havok::DecompressDeltaChunk` | **The Engine.** Performs heavy-lifting delta-decompression and interpolation between keyframes. |

### 4. Rendering Layer (Vertex Skinning)
*Applies bone movements to the 3D model mesh.*

| Address | Function Name | Role |
| :--- | :--- | :--- |
| `0x00436c70` | `Skinning::ApplyMatrices` | **The Skin.** Multiplies final bone matrices by vertex weights to transform the mesh. |
| `0x00433130` | `Skinning::BlendVertices` | Helper function for blending multiple bone influences on a single vertex. |

## References

- DFPF_ANALYSIS.md - Container format details
- MODEL_FORMAT.md - Model/skeleton info
- ComboAnim/ComboPose/Stance - Internal type names in manifests

---

*Document generated as part of Brutal Legend reverse engineering project*
