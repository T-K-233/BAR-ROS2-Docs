---
title: Add a new joint to the URDF
---

# Add a new joint to the URDF

Adding actuator number `N+1` to the robot. Walks through every file
that needs updating so the new joint is visible to URDF inspectors,
controllers, and the calibration tool. Concrete example: wiring the
3-joint neck on Lite (the `mode:=arms_neck` 17-joint variant).

## Where the joint lives

Five files in three packages:

| File | Purpose |
|---|---|
| `lite_description/robots/lite_dummy/xacro/lite_dummy.urdf.xacro` | Kinematic chain: link, joint axis, limits, mass, mesh |
| `lite_description/robots/lite_dummy/xacro/lite_dummy.ros2_control.xacro` | `<ros2_control>` block — which CAN bus, model, direction, command/state interfaces |
| `lite_description/robots/lite_dummy/mjcf/lite_dummy.xml` | MuJoCo model (if you want sim parity) |
| `humanoid_controllers/config/humanoid_control_lite_controllers.yaml` | `joints:` list for every controller + per-joint K/D / standby pose entries |
| `humanoid_bringup_lite/config/calibration.yaml` | `homing_offset` for the new joint (created via [Calibrate the zero pose](./calibrate_zero_pose.md)) |

> **Heads-up — the Lite description is generated.** The three `lite_description`
> files above are build artifacts of the external
> [`Lite-Description`](https://github.com/Berkeley-Humanoids/Lite-Description) repo,
> produced from Onshape CAD. The canonical way to add a joint is to edit
> `robots/lite_dummy/cad/*` there, run `robot-assets-generate lite_dummy`, and bump
> the `lite_description` pin in `bar.repos` — **not** to hand-edit the committed
> `xacro` / `urdf` / `mjcf`. The steps below describe the URDF changes the
> generator ultimately produces.

## Step 1 — Add the link + joint to `lite.urdf.xacro`

```xml
<link name="neck_yaw">
  <inertial> ... </inertial>
  <visual> ... </visual>
</link>

<joint name="neck_yaw" type="revolute">
  <origin xyz="..." rpy="..."/>
  <parent link="chest"/>
  <child link="neck_yaw"/>
  <axis xyz="0 0 1"/>
  <limit effort="10.0" velocity="100" lower="-0.785" upper="0.785"/>
  <joint_properties friction="0.1"/>
</joint>
```

If this is a chain (yaw → roll → pitch → head, like the neck) add
each `<link>` and `<joint>` in order.

## Step 2 — Add to `lite.ros2_control.xacro`

The xacro emits a `<joint>` entry inside the `<ros2_control>` block.
For Lite, decide which bus the new joint lives on — that drives
whether it goes into the `LiteLeftArm` block or `LiteRightArm` block,
or a new third block (e.g. a hypothetical `LiteNeck` block on a
separate `can_interface_neck`).

The neck case wants a third block:

```xml
<xacro:macro name="lite_dummy_neck_joints" params="use_fake_hardware use_sim">
  <xacro:lite_dummy_joint name="neck_yaw"   can_id="31" model="rs-00" direction="1"
                    lower_limit="-0.785" upper_limit="0.785"
                    torque_limit="10" current_limit="14"
                    use_fake_hardware="${use_fake_hardware}" use_sim="${use_sim}"/>
  <xacro:lite_dummy_joint name="neck_roll"  can_id="32" model="rs-00" direction="1"
                    lower_limit="-0.524" upper_limit="0.524"
                    torque_limit="10" current_limit="14"
                    use_fake_hardware="${use_fake_hardware}" use_sim="${use_sim}"/>
  <xacro:lite_dummy_joint name="neck_pitch" can_id="33" model="rs-00" direction="1"
                    lower_limit="-0.524" upper_limit="0.524"
                    torque_limit="10" current_limit="14"
                    use_fake_hardware="${use_fake_hardware}" use_sim="${use_sim}"/>
</xacro:macro>
```

Then for the real-hardware path, emit a third `<ros2_control>` block
that includes the new macro. For combined sim/mock, append the new
macro inside the existing combined block.

Verify the URDF expands cleanly (inside `pixi shell`):

```bash
xacro $(ros2 pkg prefix lite_description)/share/lite_description/robots/lite_dummy/xacro/lite_dummy.urdf.xacro \
    use_fake_hardware:=false use_sim:=false calibration_file:='' \
    > /tmp/expanded.urdf
```

Open the file, confirm the new joints appear with the right `<param>`
children.

## Step 3 — Update `humanoid_control_lite_controllers.yaml`

For every controller's `joints:` list, append the new joint name(s).
**Order matters** — this is the canonical joint order
([Concepts → Frozen schemas](../concepts/frozen_schemas.md)). For
backward compatibility, append at the end so existing policy
checkpoints still work:

```yaml
zero_torque_controller:
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
sit stationary — the tool's `sweep_threshold` will preserve their
existing `homing_offset` entries. Move the resulting
`./calibration.yaml` over `humanoid_bringup_lite/config/calibration.yaml`.

## Step 5 — Verify

```bash
ros2 launch humanoid_bringup_lite real.launch.py mode:=arms_neck
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
