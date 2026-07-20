# Calibrate the zero pose

Per-physical-robot recipe: regenerate `humanoid_bringup_lite/config/calibration.yaml`
so the URDF's joint zero matches your robot's encoder zero. Run this
once per robot (after assembly, after a motor swap, or after a hard
mechanical reset).

## What the calibration does

Robstride absolute encoders report a raw motor-frame position whose
zero is set at the factory. The URDF defines a different "joint zero"
based on geometric convention. The plugin bridges the two:

```
joint_pos     = direction * (raw_motor_pos - homing_offset)
raw_motor_pos = direction * joint_pos      + homing_offset
                # velocity/effort: direction only, no offset
```

`direction` (±1) is a wiring fact — it lives in the URDF. `homing_offset`
is per-physical-robot — it lives in `calibration.yaml`. This how-to
regenerates only the latter.

Full math: [Concepts → Calibration math](../concepts/calibration_math.md).

## Prerequisites

- The robot is on the bench, **arms supported** (table, jig, or a
  helper). The procedure makes the motors fully limp; gravity will
  pull unsupported arms.
- A working bringup — you've done [First real-hardware bringup](./first_real_bringup.md)
  and `/lite/joint_states` flows.
- You can comfortably move every joint through its full mechanical
  range by hand. Mechanical hard stops are the reference; the
  procedure samples them.

## Step 1 — Launch the calibration tool

```bash
cd ~/humanoid_control_ws
pixi shell
ros2 launch humanoid_bringup_lite calibrate.launch.py
```

`calibrate.launch.py` includes `real.launch.py` with three overrides:
`calibration_file:='' enable_joy_teleop:='false' enable_gamepad:='false'`.
The empty calibration means `/lite/joint_states` carries the
`direction × raw_motor_pos` frame — exactly what the homing-offset
formula needs. `zero_torque_controller` stays active, keeping every
motor at MIT(0, 0, 0, 0, 0) — fully compliant.

The terminal switches to a fixed-block live readout:

```
Move each joint through its full range, then Ctrl+C to save.

  left_shoulder_pitch     pos=+0.123  min=+0.123  max=+0.123  sweep=0.000
  left_shoulder_roll      pos=-0.456  min=-0.456  max=-0.456  sweep=0.000
  ...
```

The readout refreshes at 5 Hz, in place (ANSI cursor home). Don't
scroll — every line is the same joint as before, just updated.

## Step 2 — Hand-sweep every joint

For each of the 14 joints:

1. Move the joint **slowly to one mechanical extreme**. Watch `min`
   or `max` for that joint drop / climb.
2. Move it slowly to the **other extreme**. Watch the other column move.
3. Verify the `sweep` value reaches roughly the URDF's expected range
   (see [Hardware specs → Joint table](../reference/hardware_specs.md#joint-table)).

You don't need to sweep faster than ~2 s per direction. The tool
samples on every `/lite/joint_states` message (50 Hz) — slow is fine.

Both shoulder pitches require lifting the arm; have a helper for
those. Wrists you can do one-handed.

:::tip[Tip: bumper to bumper, not "user-friendly range"]
Push each joint until the **mechanical hard stop**. We're calibrating
to the absolute encoder limits, not to "where the arm starts to feel
stiff". A short sweep produces a small `homing_offset` error, and the
URDF limits are then over-conservative — joints will refuse to reach
their full range when commanded.
:::

## Step 3 — Save

```bash
# In the calibrate terminal:
Ctrl+C
```

The tool computes per joint:

```
lower_offset  = sampled_min - lower_limit_urdf
upper_offset  = sampled_max - upper_limit_urdf
homing_offset = 0.5 * (lower_offset + upper_offset) * direction
```

Then writes YAML to `./calibration.yaml` (cwd at launch time):

```
Wrote calibration to /home/user/humanoid_control_ws/calibration.yaml
```

If any joint had `sweep < 0.5 rad`, the tool **keeps its prior
`homing_offset`** rather than overwriting with a value derived from a
non-sweep. The list of preserved joints is printed; check it. Common
reason for un-swept joints: you ran out of hands.

If any joint's sampled range fell entirely outside the URDF range, the
tool warns about a likely **`direction` flip** in the URDF for that
joint. That's a URDF bug, not a calibration one — fix the
`<param name="direction">` in `lite.ros2_control.xacro` and recalibrate.

## Step 4 — Promote the file

```bash
cp ./calibration.yaml src/humanoid_control/humanoid_bringup_lite/config/calibration.yaml
```

That copies into the source tree. Next `colcon build` will pick it
up; or because the launch resolves the file via `FindPackageShare`,
just rebuild `humanoid_bringup_lite` to refresh the install share:

```bash
colcon build --symlink-install --packages-select humanoid_bringup_lite
```

## Step 5 — Verify

Relaunch the normal real bringup (without the calibration override):

```bash
ros2 launch humanoid_bringup_lite real.launch.py
```

Watch for the per-bus calibration-load log:

```
[ros2_control_node-1] Loaded calibration_file '...' (7/7 joints matched).
```

In a second terminal (inside the workspace env — `cd humanoid_control_ws && pixi shell`):

```bash
ros2 topic echo --once /lite/joint_states
```

Move an arm by hand to a pose you know — e.g. "arms straight down" or
"elbow at 90°" — and confirm the reported positions match. If a
shoulder pitch reads `+1.5 rad` when the arm is hanging straight, the
calibration is off by 1.5 rad for that joint; re-sweep that joint.

## Re-calibrating one joint

The tool **preserves the prior `homing_offset`** for any joint with
sweep below `sweep_threshold` (default 0.5 rad). So if you only need
to recalibrate one joint, sweep just that one through its range,
leave the others stationary, and Ctrl+C. The output will have new
values for the swept joint and the original values for everything
else.

Adjust the threshold if 0.5 rad is too generous (e.g. for joints with
< 1 rad total range):

```bash
ros2 launch humanoid_bringup_lite calibrate.launch.py sweep_threshold:=0.2
```

## See also

- [Concepts → Calibration math](../concepts/calibration_math.md) — the
  formula derivation and why it's split URDF + YAML.
- [Reference → Launch args](../reference/launch_args.md#humanoid_bringup_litelaunchcalibratelaunchpy)
  — the `output` and `sweep_threshold` args.
- The `calibrate_robot` source is ~250 lines in
  [`humanoid_bringup_lite/scripts/calibrate_robot.py`](https://github.com/Berkeley-Humanoids/humanoid_control_ros2/blob/main/humanoid_bringup_lite/scripts/calibrate_robot.py).
