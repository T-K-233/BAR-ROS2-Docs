---
title: Calibration math
---

# Calibration math

How `humanoid_devices_robstride` maps between the raw encoder reading and the
URDF joint frame, where the per-joint constants live, and why the
calibration is split across two files.

![Calibration math at the bus boundary](/img/diagrams/concepts__calibration_math__01.svg)

## The transform

For every joint:

```
read:  joint_pos     = direction · (raw_motor_pos − homing_offset)
write: raw_motor_pos = direction · joint_pos      + homing_offset
```

Velocity and effort use the same `direction`, **no offset** —
derivatives don't carry the zero-point:

```
joint_vel = direction · raw_motor_vel
joint_eff = direction · raw_motor_eff
```

Both directions are O(1) per tick, applied inside
`RobstrideSystem::read` and `RobstrideSystem::write`. Above the bus
plugin, every controller and every published `/lite/joint_states` value
is in the joint frame — controllers never see the raw encoder.

## The two parameters

| Parameter | Per | Where it lives | What it captures |
|---|---|---|---|
| `direction` | joint | URDF `<param>` inside the `<ros2_control>` block | Wiring sign — does the motor's positive direction match the URDF's positive joint direction? |
| `homing_offset` | joint | `humanoid_bringup_lite/config/calibration.yaml` | Per-physical-robot encoder zero offset (motor frame, rad). |

The split is deliberate:

- **`direction` is a wiring fact.** It depends on which way the motor
  is mounted in the assembly — same across every copy of the same
  robot design. URDF is the right home; `git` versions it; CI catches
  if you accidentally flip it.
- **`homing_offset` is per physical robot.** Two robots built from the
  same CAD will have different encoder zero points because the
  manufacturer's factory zero falls at different mechanical angles in
  each. Putting it in a YAML file the operator regenerates per-rig
  keeps the URDF clean.

## Deriving the offset

The calibration tool (`humanoid_bringup_lite/scripts/calibrate_robot.py`)
runs the plugin with `calibration_file:=''` — identity calibration —
so `/lite/joint_states` reports `direction · raw_motor_pos` (the
direction-applied-but-not-offset frame). The operator hand-sweeps each
joint to both extremes; the script samples `(min, max)` per joint.

Then per joint:

```
lower_offset  = sampled_min − URDF.lower_limit
upper_offset  = sampled_max − URDF.upper_limit
homing_offset = 0.5 · (lower_offset + upper_offset) · direction
```

The intuition: the **center** of the sampled range should land at the
center of the URDF range. The average of `(lower_offset, upper_offset)`
is the center mismatch, in joint-frame radians. Multiply by `direction`
to convert to motor-frame radians, and you have the additive offset
that the plugin's `read()` needs to subtract.

Why use both extremes rather than e.g. just sampling at a "known
home pose"? Two reasons:

1. **There is no known home pose** for the operator. You'd need a
   precision jig per arm geometry to put the joint at exactly URDF
   zero. Using mechanical hard stops removes that requirement —
   "swing the arm to its stop" is robust to operator skill.
2. **It averages out asymmetric mechanical wear.** A used motor whose
   stop has shifted 0.1 rad on one side will still report the right
   center of motion under the bisection rule.

## Why this lives in the plugin, not a controller

The transform is the **same regardless of which controller is
active**. Every controller's `update()` thinks in joint frame; only
the boundary between controllers and CAN frames cares about the
motor frame. The plugin owns that boundary.

Putting calibration in a controller would mean every controller had
to repeat the math, and any controller that forgot would silently
publish wrong positions. Putting it in the plugin means even a
debug-only `forward_command_controller` writing raw commands sees the
joint frame.

A second consequence: the standard `joint_state_broadcaster` doesn't
know calibration exists — it just publishes the state interfaces
verbatim. Because the plugin already transformed them, every `ros2
topic echo /lite/joint_states` is in joint frame for free.

## File format

`calibration.yaml` keeps the same per-joint schema as
[`T-K-233/Lite-Lowlevel-Python`](https://github.com/T-K-233/Lite-Lowlevel-Python)'s
JSON output so values move between stacks unchanged:

```yaml
left_shoulder_pitch:
  id: 11
  direction: -1
  homing_offset: 0.2817217723164135
left_shoulder_roll:
  id: 12
  direction: -1
  homing_offset: -1.3006263682400812
# ...
```

`id` and `direction` are duplicated from the URDF for human
readability — the plugin **ignores them** and reads those from the
URDF instead. Only `homing_offset` is authoritative in this file.

Why duplicate the redundant fields? They're "the operator-facing
verification": you can read the YAML and check that the IDs line up
with what you expect on your bench without cross-referencing the
URDF. The cost is that hand-edits to `id` / `direction` in
`calibration.yaml` silently have no effect.

## Edge cases the tool warns about

| Symptom in the sweep | What it usually means |
|---|---|
| `sweep < threshold` (default 0.5 rad) | Joint wasn't moved. Tool **preserves the prior `homing_offset`** for this joint rather than overwriting. |
| `sampled_min > URDF.upper_limit` OR `sampled_max < URDF.lower_limit` | The sampled range doesn't overlap the URDF range. `direction` is probably flipped in the URDF for this joint. Fix the URDF; recalibrate. |
| sweep approximately right but final `homing_offset` looks crazy | The mechanical stop isn't where the URDF expects. Check the URDF's `<limit lower="..." upper="...">` and the mechanical assembly. |

## See also

- [How-to → Calibrate the zero pose](../how_to/calibrate_zero_pose.md) — the recipe.
- [`RobstrideSystem` source](https://github.com/Berkeley-Humanoids/humanoid_control_ros2/blob/main/humanoid_devices/humanoid_devices_robstride/src/robstride_system.cpp#:~:text=load_calibration)
  — the loader + apply.
- `humanoid_bringup_lite/scripts/calibrate_robot.py` — the formula in code.
