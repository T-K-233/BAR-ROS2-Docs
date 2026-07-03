---
title: CLI tools
---

# CLI tools

Standalone executables shipped by `Humanoid Control`. The primary entry
point is the unified `hc` CLI from `humanoid_control_cli` — `hc bus ping`,
`hc bus discover`, `hc motor slider`, `hc viz rerun`, `hc viz
viser`, `hc calibrate`. Every underlying executable is also
reachable directly as `ros2 run <package> <executable>`; the `hc`
CLI is a thin verb/noun wrapper that calls `os.execvp` on those
same targets.

`humanoid_control_policy` and `pianist_policy` each ship a `prepare` console script
(the launch-time policy-artifact prep step); `pianist_policy` also ships
the `piano_state_bridge` and `midi_keyboard_driver` key-state nodes.
These are normally driven by their launch files, but are reachable via
`ros2 run …` too.

## Index

| Executable | Package | Repo | What it does |
|---|---|---|---|
| `hc` (unified CLI) | `humanoid_control_cli` | Humanoid Control | Verb/noun entry point (`hc bus ping`, `hc bus discover`, `hc motor slider`, `hc viz rerun`, …). |
| `robstride_ping` | `humanoid_devices_robstride` | Humanoid Control | Single-actuator probe (GetDeviceId / OperationStatus). Read-only. |
| `robstride_discover` | `humanoid_devices_robstride` | Humanoid Control | Scan a CAN ID range, print every device that replies. Read-only. |
| `mit_slider_gui` | `humanoid_devices_robstride` | Humanoid Control | Qt slider window publishing Float64MultiArray to a forward_command_controller. |
| `mode_manager` | `humanoid_controllers` | Humanoid Control | The FSM orchestrator. Normally launched by bringup; sometimes useful to start manually. |
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
ros2 run humanoid_devices_robstride robstride_ping --iface can0 --id 11
ros2 run humanoid_devices_robstride robstride_ping --iface can0 --id 11 --read-status

# Equivalent via the unified CLI:
hc bus ping --iface can0 --id 11
```

| Arg | Default | Description |
|---|---|---|
| `--iface` | `can0` | SocketCAN interface |
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
ros2 run humanoid_devices_robstride robstride_discover --iface can0
ros2 run humanoid_devices_robstride robstride_discover --iface can0 \
    --scan-from 1 --scan-to 127 --per-id-wait-ms 8

# Equivalent via the unified CLI:
hc bus discover --iface can0
```

| Arg | Default | Description |
|---|---|---|
| `--iface` | `can0` | SocketCAN interface |
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

### `mit_slider_gui`

```bash
ros2 run humanoid_devices_robstride mit_slider_gui
ros2 run humanoid_devices_robstride mit_slider_gui \
    --joint actuator_1 \
    --command-topic /forward_mit_controller/commands \
    --position-range -3.14 3.14 \
    --kp-range 0 10

# Equivalent via the unified CLI:
hc motor slider
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

### `mode_manager`

```bash
ros2 run humanoid_controllers mode_manager
ros2 run humanoid_controllers mode_manager --ros-args -p tick_rate_hz:=100
```

| Parameter | Default | Description |
|---|---|---|
| `tick_rate_hz` | `50.0` | Timer rate for `tick()` |
| `controller_manager` | `/controller_manager` | CM namespace |
| `joy.damp_button` | `2` | DAMP button index (default = X on Xbox) |
| `joy.quit_button` | `6` | QUIT button index (default = BACK) |
| `joy.load_combo_a` | `[4, 0]` | LOAD_A combo (default = L1+A → Pose A) |
| `joy.load_combo_b` | `[4, 1]` | LOAD_B combo (default = L1+B → Pose B) |
| `joy.start_combo_locomotion` | `[5, 0]` | START_LOCOMOTION (default = R1+A) |
| `joy.start_combo_remote` | `[5, 1]` | START_REMOTE (default = R1+B) |

Normally launched by `real.launch.py` / `mujoco.launch.py`. Useful
to run standalone when debugging the joy decoder.

Used in: [Concepts → Five-mode FSM](../concepts/five_mode_fsm.md),
[Reference → Controllers](./controllers.md#mode_manager-executable).

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
from a launch arg and brings up the rest of the stack). Standalone
invocation is useful if you already have `real.launch.py` running
with `calibration_file:=''`.

Used in: [How-to → Calibrate the zero pose](../how_to/calibrate_zero_pose.md).

### `rerun_viz` / `viser_viz`

The two live-viewer executables. **On the tethered deployment they
are spawned via `ros2 launch humanoid_bringup_lite viz.launch.py` on the
operator workstation** (`viewer:=viser` by default; `viewer:=rerun`
for the native window). Direct invocation is the single-machine
sim/dev shortcut:

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

The `--symlink-install` flag means Python scripts edit-loop without
rebuilding — useful while iterating.
