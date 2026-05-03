"""
blender_dnap_animator.py

Run this INSIDE Blender (Scripting tab → New → paste → Run Script).

Animates an existing horse armature (imported via Tannister's
doublefine_mesh_import addon) using per-frame data parsed from a dnap
animation file.

Currently writes BIND POSE keyframes for every frame (no actual
movement) — this is the placeholder until spline interpolation lands.
But it confirms the data flow:
- existing armature is found
- bone names match
- keyframes are inserted on the correct bones
- Blender's timeline shows the right frame count + FPS
"""

import bpy
import math
import os
import struct
import sys

# ────────────────────────────────────────────────────────────────────────
# CONFIG — edit these to match your setup
# ────────────────────────────────────────────────────────────────────────
ANIM_DIR = (
    r"D:\SteamLibrary\steamapps\common\BrutalLegend\DoubleFineModTool"
    r"\unpacked\characters\quadrupeds\b20_horse\animations"
)
ANIM_NAME = "sleep_breathe"   # which dnap file to animate

# Name of the armature in your scene that Tannister's addon imported.
# Check the Outliner — it's typically called "Armature" or named after
# the .Rig file (e.g., "b20_horse").
ARMATURE_NAME = "Armature"
# ────────────────────────────────────────────────────────────────────────


def parse_dnap_basic(path):
    """Read just the dnap header to get fps + frame count.
    For now we don't decode per-frame data — that requires spline interp."""
    with open(path, "rb") as f:
        d = f.read()
    if d[:4] != b"dnap":
        raise ValueError(f"Not a dnap file: {path}")
    return {
        "fps": struct.unpack_from("<f", d, 0x08)[0],
        "total_frames": struct.unpack_from("<H", d, 0x0C)[0],
        "num_quat": struct.unpack_from("<H", d, 0x34)[0],
        "num_float": struct.unpack_from("<H", d, 0x36)[0],
    }


def find_armature(name):
    arm = bpy.data.objects.get(name)
    if arm is None:
        # Try any armature in the scene
        for obj in bpy.context.scene.objects:
            if obj.type == "ARMATURE":
                arm = obj
                print(f"Auto-selected armature: {arm.name}")
                break
    if arm is None or arm.type != "ARMATURE":
        raise RuntimeError(
            f"No armature named '{name}' found and no other armature in scene. "
            f"Make sure Tannister's addon has imported the rig first."
        )
    return arm


def setup_animation(arm, num_frames, fps):
    scene = bpy.context.scene
    scene.render.fps = int(round(fps))
    scene.frame_start = 1
    scene.frame_end = num_frames

    if arm.animation_data is None:
        arm.animation_data_create()

    action_name = f"{ANIM_NAME}_action"
    action = bpy.data.actions.get(action_name)
    if action is None:
        action = bpy.data.actions.new(action_name)
    arm.animation_data.action = action

    # Switch to Pose Mode for keyframe insertion
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode="POSE")
    return action


def write_bind_pose_keyframes(arm, num_frames):
    """Insert keyframes setting every bone to identity rotation
    (i.e., the bind pose) for every frame of the animation.

    Once spline-decoded per-frame quaternions are available, replace
    the identity quaternion below with the decoded value for each
    (frame, bone) pair.
    """
    pose_bones = arm.pose.bones
    print(f"Writing {num_frames} frames × {len(pose_bones)} bones "
          f"of identity-quaternion keyframes...")

    for frame in range(1, num_frames + 1):
        bpy.context.scene.frame_set(frame)
        for pb in pose_bones:
            # Identity quaternion = no rotation relative to rest pose
            pb.rotation_mode = "QUATERNION"
            pb.rotation_quaternion = (1.0, 0.0, 0.0, 0.0)
            pb.location = (0.0, 0.0, 0.0)
            pb.keyframe_insert(data_path="rotation_quaternion", frame=frame)
            # Don't keyframe location for non-root bones in most rigs
        if frame % 50 == 0 or frame == num_frames:
            print(f"  frame {frame}/{num_frames}")

    bpy.ops.object.mode_set(mode="OBJECT")
    print("Done. Press play in the timeline.")


def main():
    dnap_path = os.path.join(ANIM_DIR, f"{ANIM_NAME}.AnimResource")
    if not os.path.exists(dnap_path):
        print(f"ERROR: not found: {dnap_path}")
        return

    info = parse_dnap_basic(dnap_path)
    print(f"Animation: {ANIM_NAME}")
    print(f"  total_frames: {info['total_frames']}")
    print(f"  fps:          {info['fps']:.2f}")
    print(f"  num_quat:     {info['num_quat']}")
    print(f"  num_float:    {info['num_float']}")

    arm = find_armature(ARMATURE_NAME)
    print(f"Targeting armature: {arm.name}  ({len(arm.data.bones)} bones)")
    setup_animation(arm, info["total_frames"], info["fps"])
    write_bind_pose_keyframes(arm, info["total_frames"])

    # Diagnostic
    sample_names = [b.name for b in list(arm.data.bones)[:6]]
    print(f"Sample bone names: {sample_names}")
    print(f"Action: {arm.animation_data.action.name}")
    print(f"FPS: {bpy.context.scene.render.fps}")
    print(f"Range: 1..{bpy.context.scene.frame_end}")


main()
