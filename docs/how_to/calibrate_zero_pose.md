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
lower_offset  = sampled_min - target_lower
upper_offset  = sampled_max - target_upper
homing_offset = 0.5 * (lower_offset + upper_offset) * direction
```

`target_lower` / `target_upper` are the URDF joint limits expressed in the
**actuator** frame — the frame the samples are in. For a direct-drive joint the
two frames coincide and these are just the URDF limits. For a joint driven
through a linkage they do not; see [Four-bar joints](#four-bar-joints-the-biped-ankle) below.

Then writes YAML to `./calibration.yaml` (cwd at launch time):

```
Wrote calibration to /home/user/humanoid_control_ws/calibration.yaml
```

### Joints the tool refuses to recompute

A joint is only recalibrated if the sweep actually reached **both** stops — the
formula assumes the sampled extremes *are* the limits. Two gates, both must pass:

| Gate | Default | Why |
|---|---|---|
| absolute sweep | `≥ 0.5 rad` | rejects a joint that never moved |
| **coverage** | `≥ 0.9` of expected travel | rejects a joint that moved *incidentally* |

The coverage gate matters because every joint is limp in zero-torque, so moving
one limb back-drives its neighbours. An absolute floor alone cannot tell 0.7 rad
of deliberate sweep from 0.7 rad of a neighbour being dragged — but as a
*fraction* the two are obvious: an incidental joint lands at 20–25 % of its
range, a swept one at 95–102 %.

Joints failing either gate **keep their prior `homing_offset`**. The list is
printed with each joint's coverage; check it.

### Warnings to read, not skip

- **`direction` flip** — a joint's sampled range fell entirely outside the URDF
  range. That's a URDF bug, not a calibration one: fix the
  `<param name="direction">` in `lite.ros2_control.xacro` and recalibrate.
- **Travel mismatch** — the joint swept a different range than the model
  predicts (`--travel-threshold`, default 0.05 rad). The two stops
  over-determine one offset, so averaging them *hides* the disagreement; the
  offset silently splits the difference and the joint zero ends up off by about
  half the residual. A persistent mismatch means a hidden transmission, soft
  stops, or wrong URDF limits.
- **Unreachable linkage** — a four-bar cannot reach a declared URDF limit, so
  the geometry or `alpha_zero` is wrong. The prior offset is preserved.

## Four-bar joints (the biped ankle)

The biped's `ankle_pitch` is not direct drive: the actuator sits in the shin and
pushes a coupler rod to a crank on the foot. The transmission ratio varies over
the range of motion, so the sampled **actuator** angle and the URDF's **joint**
angle are not the same quantity — the tool refers the URDF limits through the
linkage before differencing them.

Two things follow, and both are handled for you:

1. **The sweep must run with the linkage switched off.** With it on,
   `/lite/joint_states` reports a transformed joint angle under an as-yet-unknown
   offset, and any actuator angle outside the assemblable window reads as a hold
   — the sweep would record garbage. `calibrate.launch.py` passes
   `use_linkage:=false` automatically on the biped, the same way it forces
   `calibration_file:=''`. You'll see the plugin warn that it is reporting **raw
   actuator angles**; that is correct here and only here.

2. **The two stops become a free check on the CAD geometry.** They
   over-determine one offset, so the tool prints the actuator travel the linkage
   *predicts* against what you actually swept:

   ```
   Four-bar cross-check — actuator travel the linkage PREDICTS vs. what was measured.
     left_ankle_pitch    predicted= 84.563 deg  measured= 86.047 deg  (+1.75%)
                         [direct-drive would predict  80.000]
   ```

   This is the measurement that discriminates between the two models: a
   direct-drive assumption predicts the plain joint range (80°), the four-bar
   predicts 84.563°, and the robot answers. A couple of percent over is normal —
   the limp foot deflects against its stop. A result near the direct-drive
   number means the linkage is not being applied.

:::warning[The geometry is always published; only its *application* is gated]
`use_linkage:=false` does **not** remove the `linkage_*` params from
`/robot_description` — the mechanism is a physical fact, and the calibration
tool reads that geometry to do the referring in step 1. The flag gates only
whether the hardware plugin *applies* the transform. (An earlier version gated
the geometry itself, which silently made the whole fix inert.)
:::

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

Joints that fail either gate **keep their prior `homing_offset`**, so a partial
calibration is just a full one where you only sweep what you care about: move
that joint through its range, leave the others alone, Ctrl+C. The output carries
new values for the swept joint and the originals for everything else.

Sweep the target joint **all the way**, though — the coverage gate wants ≥ 90 %
of its travel, so a half-hearted sweep now silently preserves the old value
instead of writing a bad one.

:::danger[Priors come from the output file, not the committed config]
"The original values for everything else" means *whatever is in the `--output`
file* (default `./calibration.yaml`), **not** what is committed in
`humanoid_bringup_lite/config/`. A stale or bad output file from an earlier run
silently poisons every skipped joint — this is how one bad run's garbage
propagated into the next.

Before a partial calibration, seed the output from the good config:

```bash
cp src/humanoid_control/humanoid_bringup_lite/config/calibration.yaml ./calibration.yaml
```
:::

Both gates are tunable — loosen `sweep_threshold` for joints with < 1 rad of
total range, or `coverage` if a joint has a genuine mechanical limit short of
its URDF range:

```bash
ros2 launch humanoid_bringup_lite calibrate.launch.py sweep_threshold:=0.2
ros2 launch humanoid_bringup_lite calibrate.launch.py coverage:=0.8
```

## See also

- [Concepts → Calibration math](../concepts/calibration_math.md) — the
  formula derivation and why it's split URDF + YAML.
- [Reference → Launch args](../reference/launch_args.md#humanoid_bringup_litelaunchcalibratelaunchpy)
  — the `output`, `sweep_threshold`, `coverage` and `travel_threshold` args.
- The `calibrate_robot` source is ~250 lines in
  [`humanoid_bringup_lite/scripts/calibrate_robot.py`](https://github.com/Berkeley-Humanoids/humanoid_control_ros2/blob/main/humanoid_bringup_lite/scripts/calibrate_robot.py).
