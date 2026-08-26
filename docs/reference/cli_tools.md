---
title: Diagnostics and utility commands
---

# Diagnostics and utility commands

Standalone executables shipped by `Humanoid Control`, and the workspace
pixi tasks that wrap the common ones. Every tool is reachable as
`ros2 run <package> <executable>` — that canonical form is what the
per-tool sections below document. The frequently-used ones also have a
workspace task (`pixi run ping-bus`, `pixi run scan-bus`, …), each a
one-line wrapper over the same canonical command.

:::note[The `hc` CLI was retired]
Rev 1 of the workspace interface protocol shipped these tools behind a
packaged `hc` CLI (`humanoid_control_cli`). Rev 2 dissolved it — the
package is deleted. Its verbs became the workspace tasks in the table
below, or, for rarely-used tools, plain documented `ros2 run` commands.
See [How-to → Workspace commands](../how_to/use_pixi_tasks.md) for the
task interface itself.
:::

## Task ↔ canonical command mapping

| Former `hc` verb | Task (if any) | Canonical command |
|---|---|---|
| `hc bus ping` | `pixi run ping-bus` | `ros2 run humanoid_devices_robstride robstride_ping` |
| `hc bus discover` | `pixi run scan-bus` | `ros2 run humanoid_devices_robstride robstride_discover` |
| `hc bus probe` | `pixi run profile-bus` | `ros2 run humanoid_devices_robstride robstride_probe` |
| `hc bus probe-report` | — | `ros2 run humanoid_devices_robstride robstride_probe_report` |
| `hc motor slider` | — | `ros2 run humanoid_devices_robstride mit_slider_gui` |
| `hc viz` | `pixi run viz` | `ros2 launch humanoid_bringup_lite viz.launch.py` (`viewer:=viser` default, `viewer:=rerun`) |
| `hc viz viser` | — | `ros2 run humanoid_bringup_lite viser_viz` |
| `hc viz rerun` | — | `ros2 run humanoid_bringup_lite rerun_viz` |
| `hc viz urdf` | — | `ros2 launch humanoid_bringup_lite lite_view.launch.py` |
| `hc calibrate` | `pixi run calibrate` | `ros2 launch humanoid_bringup_lite calibrate.launch.py` |

Tasks forward trailing arguments verbatim
(`pixi run ping-bus --channel can0 --id 11`). Commands without a task are
deliberate — rarely-used tools get no alias. Run them inside
`pixi shell` as plain `ros2 run …`, or from any terminal as
`pixi run -- ros2 run …`.

`humanoid_control_policy` and `pianist_policy` each ship a `prepare` console script
(the launch-time policy-artifact prep step); `pianist_policy` also ships
the `piano_state_bridge` and `midi_keyboard_driver` key-state nodes.
These are normally driven by their launch files, but are reachable via
`ros2 run …` too.

## Index

| Executable | Package | Repo | What it does |
|---|---|---|---|
| `robstride_ping` | `humanoid_devices_robstride` | Humanoid Control | Single-actuator probe (GetDeviceId / OperationStatus). Read-only. |
| `robstride_discover` | `humanoid_devices_robstride` | Humanoid Control | Scan a CAN ID range, print every device that replies. Read-only. |
| `robstride_probe` | `humanoid_devices_robstride` | Humanoid Control | Link RTT / jitter probe against one actuator. |
| `robstride_probe_report` | `humanoid_devices_robstride` | Humanoid Control | Report companion for `robstride_probe` captures. |
| `mit_slider_gui` | `humanoid_devices_robstride` | Humanoid Control | Qt slider window publishing Float64MultiArray to a forward_command_controller. |
| `joy_teleop` | `joy_teleop` (teleop_tools) | external (built from source) | Stock gamepad node; maps buttons directly to `/controller_manager/switch_controller`. Normally launched by bringup. |
| `calibrate_robot` | `humanoid_bringup_lite` | Humanoid Control | Sample (min, max) per joint; write `calibration.yaml` on Ctrl+C. |
| `rerun_viz` | `humanoid_bringup_lite` | Humanoid Control | Native rerun viewer subscribed to `/robot_description` + `/lite/joint_states`. |
| `viser_viz` | `humanoid_bringup_lite` | Humanoid Control | Browser viewer (default port 8080). Same subscriptions. |
| `prepare` | `humanoid_control_policy` | Humanoid Control | Launch-time prep: resolve the ONNX (local / W&B), convert the LeRobot motion → `.mcap` bag, emit the `rl_policy_controller` overlay (used by `lite_policy.launch.py`). |
| `prepare` | `pianist_policy` | pianist_ros2 | Piano counterpart of `humanoid_control_policy prepare` (song → key-state `.mcap`; used by `piano_policy.launch.py`). |
| `piano_state_bridge` | `pianist_policy` | pianist_ros2 | Sim-side bridge — JointState piano keys → `std_msgs/Float32MultiArray` on `/piano/key_state`. |
| `midi_keyboard_driver` | `pianist_policy` | pianist_ros2 | USB-MIDI input → `/piano/key_state` (`std_msgs/Float32MultiArray`, real-piano counterpart of the sim bridge). |

## Per-tool reference

### `robstride_ping`

```bash
ros2 run humanoid_devices_robstride robstride_ping --channel can0 --id 11
ros2 run humanoid_devices_robstride robstride_ping --channel can0 --id 11 --read-status

# Equivalent one-line task wrapper:
pixi run ping-bus --channel can0 --id 11
```

| Arg | Default | Description |
|---|---|---|
| `--channel` | `can0` | SocketCAN interface |
| `--id` | `32` | Target Robstride device ID |
| `--timeout-ms` | `500` | How long to wait for the reply |
| `--read-status` | (off) | After GetDeviceId, also Enable → wait for OperationStatus → Disable, for a one-shot pose / fault read |

Read-only when `--read-status` is omitted. With `--read-status`, the
motor is briefly Enabled and Disabled — no MIT operation control, no
commanded motion, but the actuator does transition Enable → Disable
internally.

Used in: [Tutorials → Drive one Robstride](../tutorials/drive_one_robstride.md),
[How-to → Probe CAN bus](../how_to/probe_can_bus.md).

### `robstride_discover`

```bash
ros2 run humanoid_devices_robstride robstride_discover --channel can0
ros2 run humanoid_devices_robstride robstride_discover --channel can0 \
    --scan-from 1 --scan-to 127 --per-id-wait-ms 8

# Equivalent one-line task wrapper:
pixi run scan-bus --channel can0
```

| Arg | Default | Description |
|---|---|---|
| `--channel` | `can0` | SocketCAN interface |
| `--scan-from` | `1` | Lowest ID to ping |
| `--scan-to` | `32` | Highest ID to ping (inclusive; clamped to 127) |
| `--host-id` | `253` | Host CAN ID used in the GetDeviceId frame |
| `--per-id-wait-ms` | `8` | Gap between successive ping sends |
| `--drain-ms` | `200` | Listen window after the last ping |

Read-only — only `GetDeviceId` is sent. Background drain thread
keeps the RX ring from filling during long scans.

Exit code: `0` if anything answered, `3` if scan completed cleanly
with zero replies. Both are useful in CI.

Used in: [How-to → Probe CAN bus](../how_to/probe_can_bus.md),
[Hardware specs → Bus-bring-up checklist](./hardware_specs.md#bus-bring-up-checklist).

### `robstride_probe` / `robstride_probe_report`

```bash
# Link RTT / jitter probe against one actuator:
ros2 run humanoid_devices_robstride robstride_probe --channel can0 --ids 11
# Equivalent one-line task wrapper:
pixi run profile-bus --channel can0 --ids 11

# Report companion — rarely used, no task:
ros2 run humanoid_devices_robstride robstride_probe_report
```

`robstride_probe` measures round-trip latency and jitter on the
command → reply path for a single actuator; `robstride_probe_report`
renders the captured data into a report. The report tool is rarely
used, so it deliberately has no task wrapper.

### `mit_slider_gui`

```bash
ros2 run humanoid_devices_robstride mit_slider_gui
ros2 run humanoid_devices_robstride mit_slider_gui \
    --joint actuator_1 \
    --command-topic /forward_mit_controller/commands \
    --position-range -3.14 3.14 \
    --kp-range 0 10

# Rarely used, no task — from outside `pixi shell`:
pixi run -- ros2 run humanoid_devices_robstride mit_slider_gui
```

| Arg | Default | Description |
|---|---|---|
| `--joint` | `actuator_1` | Joint name to read from `/joint_states` |
| `--command-topic` | `/forward_mit_controller/commands` | Float64MultiArray topic to publish to |
| `--state-topic` | `/lite/joint_states` | For the live readout |
| `--position-range` | `-3.14159 3.14159` | Slider range, rad |
| `--velocity-range` | `-1.0 1.0` | rad/s |
| `--effort-range` | `-1.0 1.0` | Nm |
| `--kp-range` | `0.0 10.0` | N·m/rad |
| `--kd-range` | `0.0 1.0` | N·m·s/rad |
| `--default-kp` | `2.0` | Initial slider value |
| `--default-kd` | `0.5` | Initial slider value |

Requires `python_qt_binding` (installed alongside `rqt_reconfigure`).

Used in: [Tutorials → Drive one Robstride](../tutorials/drive_one_robstride.md),
[How-to → mit_slider_gui](../how_to/mit_slider_gui.md).

### `joy_teleop`

The stock ROS `teleop_tools` gamepad node. There is **no** `mode_manager`
executable and no FSM any more — `joy_teleop` maps gamepad buttons
**directly** to `/controller_manager/switch_controller`, driven entirely
by a YAML config (`lite_joy_teleop.yaml` / `biped_joy_teleop.yaml` /
`prime_joy_teleop.yaml`). robostack-jazzy ships no `joy_teleop` binary,
so it is built from source via `humanoid_control.repos`.

```bash
ros2 run joy_teleop joy_teleop --ros-args --params-file lite_joy_teleop.yaml
```

Each button **activates one controller and deactivates its siblings**
(flat, `BEST_EFFORT`) — any transition from any state, no gating, no
ordering. Default Lite-arm button map:

| Button(s) | Activates |
|---|---|
| `X` | `damping_controller` |
| `L1 + A` | `standby_controller_a` |
| `L1 + B` | `standby_controller_b` |
| `L1 + Y` | `standby_controller_y` |
| `R1 + A` | `rl_policy_controller` (locomotion) |
| `R1 + B` | `remote_policy_controller` |
| `BACK` | *nothing* (STOP — deactivates every mode) |

`BACK` activates nothing and the hardware holds each joint's safe state — it no longer shuts the process
down; CAN Disable still happens on `Ctrl+C` via the hardware
`on_deactivate`. Normally launched by `lite_real.launch.py` (gated on
`enable_joy_teleop`, default `true`) or `lite_mujoco.launch.py` (gated on
`enable_gamepad`, which covers both `joy_node` and `joy_teleop`). Without
a gamepad, switch controllers directly with
`ros2 control switch_controllers --activate <name> --deactivate <name>`.

Reference config pattern: `qiayuanl/unitree_bringup` `config/g1/joy.yaml`.

### `calibrate_robot`

```bash
ros2 run humanoid_bringup_lite calibrate_robot --output ./calibration.yaml
ros2 run humanoid_bringup_lite calibrate_robot \
    --output ./calibration.yaml --sweep-threshold 0.3
```

| Arg | Default | Description |
|---|---|---|
| `--output` | (required) | Path to write the resulting YAML |
| `--sweep-threshold` | `0.5` | Min sweep (rad) below which the prior `homing_offset` is preserved |

Normally launched by `calibrate.launch.py` (which sets `--output`
from a launch arg and brings up the rest of the stack) — that launch
is what the `pixi run calibrate` task wraps. Standalone
invocation is useful if you already have `lite_real.launch.py` running
with `calibration_file:=''`.

Used in: [How-to → Calibrate the zero pose](../how_to/calibrate_zero_pose.md).

### `rerun_viz` / `viser_viz`

The two live-viewer executables. **On the tethered deployment they
are spawned via `ros2 launch humanoid_bringup_lite viz.launch.py` on the
operator workstation** (`viewer:=viser` by default; `viewer:=rerun`
for the native window) — that launch is what the `pixi run viz` task
wraps. Direct invocation is the single-machine sim/dev shortcut (no
task; run inside `pixi shell` or via `pixi run --`):

```bash
ros2 run humanoid_bringup_lite rerun_viz       # native rerun window
ros2 run humanoid_bringup_lite viser_viz       # browser viewer at http://0.0.0.0:8080
```

Both read `/robot_description` (latched) once, subscribe to a
`--joint-state-topic` (default `/lite/joint_states`), and render the
live pose. `rerun-sdk`, `viser`, `yourdfpy`, and `scipy` ship in
the workspace env.

Used in: [How-to → Live viz](../how_to/live_viz.md),
[Concepts → Architecture → Deployment topology](../concepts/architecture.md#deployment-topology).

## Adding a new CLI tool

For a tool that ships from one of the existing packages:

1. Drop the source in `<package>/scripts/<name>.py` (Python) or
   `<package>/src/<name>.cpp` (C++).
2. In the package's `CMakeLists.txt`, install it under
   `lib/${PROJECT_NAME}` *without* the `.py` extension so
   `ros2 run` finds it:
   ```cmake
   install(
     PROGRAMS scripts/<name>.py
     DESTINATION lib/${PROJECT_NAME}
     RENAME <name>
   )
   ```
   For C++ add the executable target and install it normally — the
   `install(TARGETS ... RUNTIME DESTINATION ...)` lines.
3. Rebuild with `colcon build --symlink-install --packages-select <package>`.
4. Verify with `ros2 pkg executables <package>`.
5. Only if the tool will be used often: add a one-line wrapper task to
   the reference block in
   [How-to → Workspace commands](../how_to/use_pixi_tasks.md#the-reference-block)
   so every workspace inherits the same alias. Rarely-used tools stay
   task-less by design.

The `--symlink-install` flag means Python scripts edit-loop without
rebuilding — useful while iterating.
