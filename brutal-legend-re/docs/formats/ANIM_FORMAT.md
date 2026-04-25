# Animation/Skeleton Format

**Status:** In Progress
**Game:** Brutal Legend
**Engine:** Buddha (Double Fine)
**Updated:** 2026-04-01

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
| .AnimResource | Animation Data |
| .AnimResource.header | Animation data header |

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

## References

- DFPF_ANALYSIS.md - Container format details
- MODEL_FORMAT.md - Model/skeleton info
- ComboAnim/ComboPose/Stance - Internal type names in manifests

---

*Document generated as part of Brutal Legend reverse engineering project*
