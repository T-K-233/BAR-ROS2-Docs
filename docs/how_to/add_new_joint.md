---
title: Add a new joint to the URDF
---

# Add a new joint to the URDF

Adding actuator number `N+1` to the robot. This guide walks through every file that
needs updating, so the new joint reaches URDF inspectors, controllers, and the
calibration tool. The running example wires the 3-joint neck on Lite.

## Where the joint lives

The description artifacts are **generated**, so you edit generation inputs, never the
`xacro` / `urdf` / `mjcf` files themselves. Those live in the external
[`Lite-Description`](https://github.com/Berkeley-Humanoids/Lite-Description) repo.

| File | Purpose |
|---|---|
| `Lite-Description` `robots/lite_dummy/cad/config.json` | Onshape document and export options: the kinematic chain comes from CAD |
| `Lite-Description` `robots/lite_dummy/cad/joint_properties.json` | Sim tuning per joint: `armature`, `friction_loss`, `effort_limit` |
| `Lite-Description` `robots/lite_dummy/cad/ros2_control.json` | Hardware map: which CAN bus, CAN id, model, direction, torque and current caps |
| `humanoid_bringup_lite/config/lite_controllers.yaml` | `joints:` list for every controller, plus per-joint K/D and standby pose entries |
| `config/calibration.yaml` (deployment workspace) | `homing_offset` for the new joint (created via [Calibrate the zero pose](./calibrate_zero_pose.md)) |

:::warning
Do not hand-edit `robots/<variant>/xacro/`, `urdf/` or `mjcf/`. Every one of those
files carries a `GENERATED ... Do not edit by hand` banner, and
`robot-assets-generate` overwrites them. A test asserts that the committed xacro
equals a fresh generation, so a hand edit fails CI.
:::

## Step 1 — Add the joint in CAD, then export

The kinematics come from Onshape. Add the link and joint there, then re-export:

```bash
cd Lite-Description
uv run robot-assets-generate lite_dummy --force
```

Give the new joint an entry in `cad/joint_properties.json` so the MJCF and the URDF
effort limit are complete. An exact name or a regex key both work:

```json
"neck_(roll|pitch|yaw)": {
    "armature": 0.005,
    "friction_loss": 0.1,
    "effort_limit": 10.0
}
```

The generator raises an error for any joint with no matching entry, so a missed joint
cannot reach the MJCF silently.

## Step 2 — Map the joint to hardware in `ros2_control.json`

Decide which CAN bus the joint sits on. A joint on an existing bus only needs an entry
in `joints`. A joint on a new bus also needs a `groups` entry, which becomes its own
`<ros2_control>` block on the real-hardware path.

```json
"groups": [
    {"name": "left_arm",  "block_name": "LiteLeftArm",  "can_interface_arg": "can_interface_left"},
    {"name": "right_arm", "block_name": "LiteRightArm", "can_interface_arg": "can_interface_right"},
    {"name": "neck",      "block_name": "LiteNeck",     "can_interface_arg": "can_interface_neck"}
],

"joints": [
    {"name": "neck_yaw",   "group": "neck", "can_id": 31, "model": "rs-00", "direction": 1, "torque_limit": 10, "current_limit": 14},
    {"name": "neck_roll",  "group": "neck", "can_id": 32, "model": "rs-00", "direction": 1, "torque_limit": 10, "current_limit": 14},
    {"name": "neck_pitch", "group": "neck", "can_id": 33, "model": "rs-00", "direction": 1, "torque_limit": 10, "current_limit": 14}
]
```

A new `can_interface_neck` also needs an entry in `args`, so the assembly declares it as
a xacro arg. Position limits are **not** declared here: the generator reads them from the
URDF, which comes from CAD.

:::note
Every group must list at least one joint. The generator rejects a group with none,
because the emitted bus block would call a macro that was never defined.
:::

Regenerate and expand to check the result (inside `pixi shell`):

```bash
uv run robot-assets-generate lite_dummy --only xacro

xacro $(ros2 pkg prefix lite_description)/share/lite_description/robots/lite_dummy/xacro/lite_dummy.urdf.xacro \
    use_mock_hardware:=false sim_mujoco:=false calibration_file:='' \
    > /tmp/expanded.urdf
```

Open the file and confirm the new joints appear with the right `<param>` children.

## Step 3 — Update `lite_controllers.yaml`

For every controller's `joints:` list, append the new joint name(s).
**Order matters** — this is the canonical joint order
([Concepts → Frozen schemas](../concepts/frozen_schemas.md)). For
backward compatibility, append at the end so existing policy
checkpoints still work:

```yaml
damping_controller:
  ros__parameters:
    joints:
      - left_shoulder_pitch
      - ...
      - right_wrist_pitch
      - neck_yaw           # NEW
      - neck_roll          # NEW
      - neck_pitch         # NEW
```

For controllers with per-joint arrays (`target_stiffness`,
`damping`, `pose_segment_<N>`, etc.) extend those by the matching
length. Use the same K/D as a similar-class joint as a starting
point:

```yaml
standby_controller_a:
  ros__parameters:
    joints: [...]    # length 17 now
    target_stiffness: [20, 20, ..., 20, 30, 30, 30]   # was 14 entries, now 17
    target_damping:   [ 2,  2, ...,  2,  1,  1,  1]
    pose_segment_0: [0, 0, ..., 0, 0, 0, 0]            # arms-down + neck-zero
    pose_segment_1: [0.3, -1.0, ..., -0.3, 0, 0, 0]    # piano-ready + neck-zero
```

STANDBY now has two poses, each a separate spawned instance of the same
plugin with its own params block — `standby_controller_a` (Pose A) and
`standby_controller_b` (Pose B). Both blocks own per-joint arrays, so
extend **both** the same way when you add a joint: the arrays in
`standby_controller_b:` must grow to the new length too.

## Step 4 — Calibrate

Once the URDF + YAML are updated and the build is clean, plug in the
new motor and run:

```bash
ros2 launch humanoid_bringup_lite calibrate.launch.py
```

Hand-sweep the new joint(s) through their full range. Old joints
sit stationary — the tool's sweep threshold will preserve their
existing `homing_offset` entries. Move the resulting
`./calibration.yaml` over the deployment workspace's `config/calibration.yaml`.

## Step 5 — Verify

```bash
ros2 launch humanoid_bringup_lite lite_real.launch.py
```

In a second terminal:

```bash
cd humanoid_control_ws && pixi shell
# Should now see 14 + new joints in /lite/joint_states
ros2 topic echo --once /lite/joint_states | grep -c " - " # name count
```

If the new joint shows `0.0` exactly while others have real values,
the calibration didn't pick it up — re-run Step 4 and confirm the
YAML has an entry with the expected joint name.

## Step 6 — Update docs

Two places at minimum:

- [`reference/hardware_specs.md`](../reference/hardware_specs.md) — add the new joint(s) to the joint table.
- [`getting_started/intro.md`](../getting_started/intro.md) — update the joint count if it's mentioned.
- Anywhere else that mentions a hard-coded joint count.

## Caveat — what breaks for existing policies

Appending at the end is the safest change, but it isn't free:

- The 17-element observation vector is longer than the 14-element one
  any pre-existing policy was trained against. Old `.onnx` files
  consume only the first 14; new ones can use 17.
- The `joint_names` array in `MITCommand` messages must match the
  active controller's claimed joints. If you publish a 14-element
  array to a 17-joint controller, it's rejected.
- Topic bag recordings from before the change won't replay against
  the new controllers without a remap.

Inserting or reordering — as opposed to appending — would invalidate
**every** existing policy. Avoid unless you commit to retraining
everything.

## See also

- [Concepts → Frozen schemas](../concepts/frozen_schemas.md) — joint-order freezing rules.
- [Calibrate the zero pose](./calibrate_zero_pose.md) — calibration for the new joint.
- [Reference → Hardware specs](../reference/hardware_specs.md).
