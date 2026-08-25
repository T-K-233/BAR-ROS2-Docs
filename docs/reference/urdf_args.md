---
title: URDF / xacro args
---

# URDF / xacro args

Full surface of the xacro arguments and per-joint URDF parameters
that `lite_description` (the `lite_dummy` variant) exposes. The launch files
([Reference → Launch args](./launch_args.md)) wrap these — usually
you'll only touch them directly when driving xacro from a script or
extending the URDF.

## Top-level xacro arguments

Declared in `lite_description/robots/lite_dummy/xacro/lite_dummy.urdf.xacro`:

| Arg | Default | Effect |
|---|---|---|
| `use_mock_hardware` | `true` | Select `mock_components/GenericSystem` — single combined `<ros2_control>` block. |
| `sim_mujoco` | `false` | **Wins over `use_mock_hardware`** — select `mujoco_ros2_control/MujocoSystem`, single combined block. |
| `can_interface_left` | `can0` | SocketCAN interface for the **left** arm (real-hardware path only). |
| `can_interface_right` | `can1` | SocketCAN interface for the **right** arm (real-hardware path only). |
| `calibration_file`    | `""` | Absolute path to the per-physical-robot calibration YAML. Empty = identity calibration. |

The biped variants (`lite_biped`, `lite_biped_debug`) add two more: `imu_port` for the
base IMU's serial device, and `use_linkage`, which switches whether the plugin applies
the ankle four-bar transform. Calibration sets `use_linkage:=false` because it needs raw
actuator angles.

:::note[`hardware_config` is a *launch* arg, not a xacro arg]
The xacro takes the two bus names directly (`can_interface_left` /
`can_interface_right`). `hardware_config` is a **launch** argument
([Reference → Launch args](./launch_args.md)): `lite_real.launch.py` reads the
`buses:` section of that YAML and passes the resulting ifnames into the
two xacro args above. You only set `hardware_config` when launching, not
when driving xacro by hand.
:::

The xacro selects between three plugin paths based on these:

```
sim_mujoco:=true                             -> mujoco_ros2_control/MujocoSystem
use_mock_hardware:=true (sim_mujoco:=false)  -> mock_components/GenericSystem
(both false)                                 -> humanoid_devices_robstride/RobstrideSystem
```

`sim_mujoco` wins over `use_mock_hardware`. The naming follows the
Universal_Robots_ROS2_Description convention: one boolean per non-real backend, real
hardware as the fallback. See
[Concepts → Hardware backend selection](../concepts/hardware_backend_selection.md) for why
these two args are named this way, and note that `sim_mujoco` is unrelated to the
`use_sim_time` node parameter.

## `<ros2_control>` block structure

On the **real-hardware path** the xacro emits **two** `<ros2_control>`
blocks:

```xml
<ros2_control name="LiteLeftArm" type="system">
  <hardware>
    <plugin>humanoid_devices_robstride/RobstrideSystem</plugin>
    <param name="can_interface">${can_interface_left}</param>   <!-- can_interface_left arg -->
    <param name="calibration_file">${calibration_file}</param>
  </hardware>
  <!-- 7 <joint> blocks, ids 11..17 -->
</ros2_control>

<ros2_control name="LiteRightArm" type="system">
  <hardware>
    <plugin>humanoid_devices_robstride/RobstrideSystem</plugin>
    <param name="can_interface">${can_interface_right}</param>  <!-- can_interface_right arg -->
    <param name="calibration_file">${calibration_file}</param>
  </hardware>
  <!-- 7 <joint> blocks, ids 21..27 -->
</ros2_control>
```

On the **sim / mock paths** the xacro emits one combined block with
all joints (no `can_interface`, no `calibration_file`).

## Hardware-level `<param>`s (real-hardware path)

Inside the `<hardware>` element of each `<ros2_control>` block:

| Param | Type | Default | Description |
|---|---|---|---|
| `can_interface` | string | (required) | SocketCAN interface name |
| `calibration_file` | string | `""` | YAML calibration path; empty = identity |
| `host_id` | int (1–255) | `0xFD` | Host CAN id used in Enable / Disable / WriteParameter frames |
| `rx_timeout_ms` | int | `200` | Per-joint silence threshold before `FLAG_RX_TIMEOUT` is raised |
| `write_firmware_limits` | bool | `false` | When `true`, push per-joint `torque_limit` / `current_limit` to actuator firmware via WriteParameter on activate. Off by default because the burst writes overflow some adapters' TX FIFOs. |

## Per-joint `<param>`s (every backend)

Inside each `<joint>` element. The `lite_dummy_joint` xacro macro emits these on
**every** backend, not just the real one: `MujocoSystem` reads only `mimic` and
`multiplier` from a joint's params, and `mock_components/GenericSystem` ignores the rest,
so the joint macros stay backend-agnostic and no hardware switch reaches a `<joint>`.

| Param | Type | Required? | Description |
|---|---|---|---|
| `can_id` | int (1–127) | **yes** | CAN node ID |
| `model` | string (`rs-00`..`rs-06`) | no (default `rs-02`) | Drives the MIT scaling limits (pos / vel / torque / kp / kd) |
| `direction` | ±1 | no (default `1`) | Wiring sign flip applied at the bus boundary |
| `lower_limit` | float (rad) | no (default `-∞`) | Joint-frame lower clip applied to command before encode |
| `upper_limit` | float (rad) | no (default `+∞`) | Joint-frame upper clip — same |
| `torque_limit` | float (Nm) | no (default `0` = skip firmware write) | Per-joint firmware torque limit (only written when `write_firmware_limits:=true`) |
| `current_limit` | float (A) | no (default `0` = skip) | Same, firmware current limit |

The `model` strings correspond to specific Robstride product
families:

| model | Robstride product | Position lim | Torque lim | K_p max | K_d max |
|---|---|---:|---:|---:|---:|
| `rs-00` | RS00 | ±4π | 14 Nm | 500 | 5 |
| `rs-01` | RS01 | ±4π | 17 Nm | 500 | 5 |
| `rs-02` | RS02 | ±4π | 17 Nm | 500 | 5 |
| `rs-03` | RS03 | ±4π | 60 Nm | 5000 | 100 |
| `rs-04` | RS04 | ±4π | 120 Nm | 5000 | 100 |
| `rs-05` | RS05 | ±4π | 5.5 Nm | 500 | 5 |
| `rs-06` | RS06 | ±4π | 36 Nm | 5000 | 100 |

These are the **wire-side scaling caps**, not your operating limits.
A scaled-to-±limit u16 is mapped to the wire range; commands beyond
the limits saturate. Per-joint `torque_limit` is a softer, firmware-
enforced limit on top of these.

## Per-joint command / state interfaces (every backend)

Independent of which plugin is selected, every `<joint>` block emits
the same 5 command interfaces and 3 state interfaces:

```xml
<joint name="${name}">
  <command_interface name="position"/>
  <command_interface name="velocity"/>
  <command_interface name="effort"/>
  <command_interface name="stiffness"/>
  <command_interface name="damping"/>
  <state_interface name="position"/>
  <state_interface name="velocity"/>
  <state_interface name="effort"/>
  <!-- per-joint <param> children, on every backend -->
</joint>
```

The interface names are **not** arbitrary — they match
`mujoco_ros2_control::MujocoSystem`'s constants verbatim. See
[Concepts → MIT command surface](../concepts/mit_command_surface.md).

## Driving xacro directly

Useful when scripting URDF expansion (e.g. in a sim2sim eval
harness):

Run these inside `pixi shell` (so `xacro` / `ros2 pkg` are on PATH):

```bash
cd humanoid_control_ws && pixi shell

# Mock / RViz path
xacro $(ros2 pkg prefix lite_description)/share/lite_description/robots/lite_dummy/xacro/lite_dummy.urdf.xacro \
    use_mock_hardware:=true \
    > /tmp/lite_mock.urdf

# MuJoCo path
xacro $(ros2 pkg prefix lite_description)/share/lite_description/robots/lite_dummy/xacro/lite_dummy.urdf.xacro \
    sim_mujoco:=true \
    > /tmp/lite_sim.urdf

# Real-hardware path
xacro $(ros2 pkg prefix lite_description)/share/lite_description/robots/lite_dummy/xacro/lite_dummy.urdf.xacro \
    use_mock_hardware:=false sim_mujoco:=false \
    can_interface_left:=can0 can_interface_right:=can1 \
    calibration_file:=/abs/path/to/calibration.yaml \
    > /tmp/lite_real.urdf
```

`ros2_control_node` does this internally when started by the launch
files. You'd run xacro directly mainly for debugging URDF expansion
errors.

## See also

- [Reference → Hardware specs](./hardware_specs.md) — the canonical
  per-joint values these params take on Lite.
- [Reference → Launch args](./launch_args.md) — how the launch files
  feed these xacro args.
- [Concepts → MIT command surface](../concepts/mit_command_surface.md)
  — why the interface set is what it is.
- [How-to → Add a new joint](../how_to/add_new_joint.md) — recipe for
  extending the URDF.
- [Concepts → Hardware backend selection](../concepts/hardware_backend_selection.md)
  — why the backend args are shaped and named the way they are.
