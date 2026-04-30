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

## Associated Functions

1. The "Game Logic" Layer (Brutal Legend Custom Code)
These functions are part of the CoSkeleton class, which is Brutal Legend's wrapper around the Havok engine.

|Function Address|	|Descriptive Name|	|Role|
|FUN_00a89af0|	CoSkeleton::Constructor	Initializes a new skeleton instance. Sets up default values and assigns the VFTABLE.|
|FUN_00a89bf0|	CoSkeleton::Destructor	Cleans up memory and releases references when a character is removed from the game.|
|FUN_00a89f50|	CoSkeleton::InitializeState	Allocates memory for the animation state (pose buffer) and links it to the hkaAnimatedSkeleton. Called when an animation starts.|
|FUN_00a8a530|	CoSkeleton::SyncState	Checks if the animation state has changed (e.g., switching from "Walk" to "Run") and updates internal caches.|
|FUN_00a8a580|	CoSkeleton::CleanupState	Frees the pose buffer and resets pointers when an animation stops.|
|FUN_00a8b230|	CoSkeleton::CreateUpdateJob	The "Job Factory." It creates a TaskInstance and assigns the function pointers (FUN_00a8b770) that will run on a worker thread.|
|FUN_006b40a0|	CoSkeleton::SubmitSkinningJob	Submits the final "Skinning" job to the multi-threaded system to move the 3D mesh vertices.|

2. The "Captain" Layer (The Update Loop)
This is the code that actually runs every frame to move the bones.

Function Address	Descriptive Name	Role
FUN_00a8b770	AnimationJob::Execute	The Captain. The main loop that iterates through all bones/tracks. It calls the time-advance and sampling functions.
FUN_00a8bdd0	Track::AdvanceTime	Called by the Captain. It updates the internal "clock" for specific animation tracks using the delta time.
FUN_00a8c110	Track::SamplePose	Called by the Captain. It asks the Havok engine for the new bone positions at the current time and returns a "dirty" mask.
3. The "Havok Engine" Layer (Internal Math)
These functions are inside the Havok library (00dc... and 00dd... range). They handle the complex compression math.

Function Address	Descriptive Name	Role
FUN_00dccfb0	hkaDeltaCompressedAnimation::samplePartialPose	The Sampler. The main Havok function that calculates the final bone transforms for a specific moment in time.
FUN_00dd7b00	Havok::DecodeBoneTransform	The Decoder. Takes compressed data (quaternions/floats) and decodes it into usable bone rotation/position data.
FUN_00dcca40	Havok::DecompressDeltaChunk	The Engine. The heavy-lifting math function that performs the actual delta-decompression and interpolation between keyframes.
4. The "Rendering" Layer (Vertex Skinning)
This is the final step where the bone movements are applied to the 3D model.

Function Address	Descriptive Name	Role
FUN_00436c70	Skinning::ApplyMatrices	The Skin. Takes the final bone matrices and multiplies them by the vertex weights to move the character's mesh.
FUN_00433130	Skinning::BlendVertices	A helper function used during skinning to blend between different bone influences on a single vertex.

## References

- DFPF_ANALYSIS.md - Container format details
- MODEL_FORMAT.md - Model/skeleton info
- ComboAnim/ComboPose/Stance - Internal type names in manifests

---

*Document generated as part of Brutal Legend reverse engineering project*
