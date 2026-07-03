---
id: quick_reference
title: Quick reference
sidebar_label: Quick reference
---

# Quick reference

Dense, scannable lookup for the most common commands, topics, and
parameters. The cheat sheet you print or pin to a second monitor.
Every link points at the page with the full details.

All commands below assume you've entered the workspace env (e.g.
`cd humanoid_control_ws && pixi shell`) so `ros2`, `colcon`, and the Humanoid Control console
scripts are on `PATH`. Looking for one-line aliases (`pixi run
launch-mujoco`, `pixi run build`, …)?  See
[How-to → Workspace shortcuts with pixi](../how_to/use_pixi_tasks.md).

## Launch invocations

Grouped by which machine they run on. See
[Concepts → Architecture → Deployment topology](../concepts/architecture.md#deployment-topology)
for the split rationale. Launches come from two repos:

- `Humanoid Control` ships the Lite + Prime bringups (`humanoid_bringup_lite`,
  `humanoid_bringup_prime`), the description viewer (`humanoid_bringup_lite`),
  and the policy prepare-and-load launch (`humanoid_control_policy`).
- `pianist_ros2` ships the piano-task launches (`pianist_bringup`
  composes a Lite + piano MuJoCo scene; `pianist_policy` prepares the
  piano policy and runs the USB-MIDI driver).

### Single-machine sim / dev (no robot, no tether)

```bash
# Drag joints in RViz — no controllers, no physics
ros2 launch humanoid_bringup_lite view_lite.launch.py

# MuJoCo sim — full controller stack, /clock from sim time
ros2 launch humanoid_bringup_lite mujoco.launch.py

# Lite + piano in MuJoCo (pianist_bringup composes the scene, spawns piano_state_bridge)
ros2 launch pianist_bringup mujoco.launch.py

# Calibrate the zero pose (writes ./calibration.yaml on Ctrl+C)
ros2 launch humanoid_bringup_lite calibrate.launch.py
```

### Robot onboard computer (real bringup)

```bash
# Real Lite — both buses, two ros2_control blocks, gamepad + mode_manager
ros2 launch humanoid_bringup_lite real.launch.py

# Real Lite, no gamepad attached (drive the FSM via /humanoid_control/mode/* services)
ros2 launch humanoid_bringup_lite real.launch.py enable_gamepad:=false

# Gamepad enumerated as js1 (multiple controllers plugged into the Jetson)
ros2 launch humanoid_bringup_lite real.launch.py joy_dev:=/dev/input/js1

# Real Lite, no FSM (raw debug / calibration)
ros2 launch humanoid_bringup_lite real.launch.py enable_mode_manager:=false
```

`real.launch.py` boots the real-time control plane only — visualisers
live on the operator workstation; the in-process policy is prepared and
loaded on the robot below.

### Robot onboard computer (prepare + load a policy)

```bash
# Prepare + load the in-process tracking policy (Humanoid Control → humanoid_control_policy):
# runs `prepare` (ONNX → .mcap + overlay), then loads rl_policy_controller
# inactive. START_LOCOMOTION (R1+A) activates it.
ros2 launch humanoid_control_policy lite_policy.launch.py \
    wandb_run_path:=… wandb_checkpoint_name:=model.onnx

# Piano policy (pianist_ros2 → pianist_policy); task picked by ONNX task_type
ros2 launch pianist_policy piano_policy.launch.py \
    wandb_run_path:=… motion_file:=/path/to/song

# USB-MIDI keyboard driver — publishes /piano/key_state (Float32MultiArray)
ros2 launch pianist_policy midi_keyboard_driver.launch.py
```

### Operator workstation (host side of the tether)

```bash
# Live URDF + /lite/joint_states viewer (humanoid_bringup_lite)
ros2 launch humanoid_bringup_lite viz.launch.py                  # viser, http://0.0.0.0:8080
ros2 launch humanoid_bringup_lite viz.launch.py viewer:=rerun    # native rerun window
```

Both machines must share `ROS_DOMAIN_ID`. Full surface:
[Launch args](./launch_args.md).

## CAN bus setup

```bash
# One-time, after USB-to-CAN adapters plug in
sudo ip link set can0 down 2>/dev/null
sudo ip link set can0 up type can bitrate 1000000
sudo ip link set can1 down 2>/dev/null
sudo ip link set can1 up type can bitrate 1000000

# Check state (look for "UP" and "ERROR-ACTIVE")
ip -d link show can0
ip -d link show can1
```

## Diagnostic CLIs

These are the `hc` (humanoid_control_cli) verbs — equivalent `ros2 run humanoid_devices_robstride …`
invocations are listed in [CLI tools](./cli_tools.md).

```bash
# Scan an ID range; read-only, no Enable
hc bus discover --iface can0 --scan-to 32
hc bus discover --iface can1 --scan-to 32

# One-shot GetDeviceId / OperationStatus probe
hc bus ping --iface can0 --id 11

# Per-joint slider window (forward_command_controller frontend)
hc motor slider

# Live URDF + /lite/joint_states viewers (single-machine sim/dev shortcuts;
# on the tethered host, prefer `ros2 launch humanoid_bringup_lite viz.launch.py`)
hc viz viser                            # browser at :8080
hc viz rerun                            # native rerun window
```

## Mode-FSM gamepad bindings (Xbox layout)

| Buttons | Intent | Allowed from | Activates |
|---|---|---|---|
| `X` | DAMP | any state | `damping_controller` |
| `L1 + A` | LOAD_A | DAMPING | `standby_controller_a` (Pose A) |
| `L1 + B` | LOAD_B | DAMPING | `standby_controller_b` (Pose B) |
| `R1 + A` | START_LOCOMOTION | STANDBY (gated on `is_finished`) | `rl_policy_controller` |
| `R1 + B` | START_REMOTE | STANDBY (gated on `is_finished`) | `remote_policy_controller` |
| `BACK` | QUIT | ZERO_TORQUE or DAMPING only | `rclcpp::shutdown()` |

`L1+A` and `L1+B` load **different poses** (`standby_controller_a` /
`standby_controller_b`); the START combo picks the policy. Pose and policy are
independent — from either pose, `R1+A` → LOCOMOTION or `R1+B` → REMOTE. You
cannot switch A↔B directly (LOAD is admissible only from DAMPING); DAMP first,
then load the other pose. See [Concepts → Five-mode FSM](../concepts/five_mode_fsm.md).

## Manual controller switching (no FSM)

These are interactive `ros2 control` calls:

```bash
# ZERO_TORQUE → DAMPING
ros2 control switch_controllers \
    --deactivate zero_torque_controller \
    --activate   damping_controller

# DAMPING → STANDBY Pose A (motors will move to the ready pose over ~4 s;
# use standby_controller_b for Pose B)
ros2 control switch_controllers \
    --deactivate damping_controller \
    --activate   standby_controller_a

# Back to safe
ros2 control switch_controllers \
    --deactivate <whatever>_controller \
    --activate   zero_torque_controller
```

Always end a session with `zero_torque_controller` active before
`Ctrl+C`-ing the launch.

## Topics you actually echo

| Topic | Type | Rate | When |
|---|---|---|---|
| `/lite/joint_states` | `sensor_msgs/JointState` | 50 Hz real / 200 Hz sim | always (`joint_state_broadcaster`, remapped at bringup) |
| `/imu/data` | `sensor_msgs/Imu` | sensor-rate | always; RELIABLE |
| `/control_mode` | `humanoid_control_msgs/ControlMode` | 50 Hz | always (`mode_manager`) |
| `/safety_status` | `humanoid_control_msgs/SafetyStatus` | on-change, latched | TRANSIENT_LOCAL; `source` field per bus |
| `/standby_controller_a/state` | `humanoid_control_msgs/StandbyState` | active-only | TRANSIENT_LOCAL; Pose A. Watch for `is_finished:true` before R1+A/R1+B |
| `/standby_controller_b/state` | `humanoid_control_msgs/StandbyState` | active-only | TRANSIENT_LOCAL; Pose B. Watch the instance matching the loaded pose |
| `/remote_policy_controller/command` | `humanoid_control_msgs/MITCommand` | source rate | when a System 1/2 source (gravity-comp, VLA) feeds `remote_policy_controller` |
| `/piano/key_state` | `std_msgs/Float32MultiArray` | sensor / sim rate | piano runs only (RELIABLE + KEEP_LAST(1)); live key state, in-process `key_pressed` term |
| `/joy` | `sensor_msgs/Joy` | sensor-rate | when `enable_gamepad:=true` (default) |

## Common one-liners

```bash
# Live controller state
ros2 control list_controllers

# Rate of /lite/joint_states (50 Hz real, 200 Hz MuJoCo)
ros2 topic hz /lite/joint_states

# Read the current pose (post-calibration, joint frame)
ros2 topic echo --once /lite/joint_states

# Safety status of every active bus
ros2 topic echo --once /safety_status

# Drive an FSM transition without a gamepad
ros2 service call /humanoid_control/mode/damp std_srvs/srv/Trigger
ros2 service call /humanoid_control/mode/load_a std_srvs/srv/Trigger   # Pose A (load_b for Pose B)

# Fake a System 1/2 MITCommand publish (when remote_policy_controller is active in MuJoCo)
ros2 topic pub --once /remote_policy_controller/command \
    humanoid_control_msgs/msg/MITCommand "{header: {stamp: now}, joint_names: [...], ...}"
```

## Services for FSM transitions

`std_srvs/Trigger` services on `/humanoid_control/mode/*` mirror the gamepad
intents — useful when there's no joystick attached.

| Service | Effect |
|---|---|
| `/humanoid_control/mode/damp` | → DAMPING from any state |
| `/humanoid_control/mode/load_a` | DAMPING → STANDBY (Pose A, `standby_controller_a`) |
| `/humanoid_control/mode/load_b` | DAMPING → STANDBY (Pose B, `standby_controller_b`) |
| `/humanoid_control/mode/start_remote` | STANDBY → REMOTE (gated on `is_finished`) |
| `/humanoid_control/mode/start_locomotion` | STANDBY → LOCOMOTION (gated on `is_finished`) |
| `/humanoid_control/mode/quit` | exit (only from ZERO_TORQUE or DAMPING) |

## The Lite joint table

14 actuated DOFs across two buses. Order is canonical (see
[Concepts → Frozen schemas](../concepts/frozen_schemas.md)).

| Idx | Joint | CAN id | Bus | Model |
|---|---|---:|---|---|
| 0 | `left_shoulder_pitch`  | 11 | can0 | rs-02 |
| 1 | `left_shoulder_roll`   | 12 | can0 | rs-00 |
| 2 | `left_shoulder_yaw`    | 13 | can0 | rs-00 |
| 3 | `left_elbow_pitch`     | 14 | can0 | rs-00 |
| 4 | `left_wrist_yaw`       | 15 | can0 | rs-05 |
| 5 | `left_wrist_roll`      | 16 | can0 | rs-05 |
| 6 | `left_wrist_pitch`     | 17 | can0 | rs-05 |
| 7 | `right_shoulder_pitch` | 21 | can1 | rs-02 |
| 8 | `right_shoulder_roll`  | 22 | can1 | rs-00 |
| 9 | `right_shoulder_yaw`   | 23 | can1 | rs-00 |
| 10 | `right_elbow_pitch`   | 24 | can1 | rs-00 |
| 11 | `right_wrist_yaw`     | 25 | can1 | rs-05 |
| 12 | `right_wrist_roll`    | 26 | can1 | rs-05 |
| 13 | `right_wrist_pitch`   | 27 | can1 | rs-05 |

Full table (effort / current limits / per-joint K/D) in
[Hardware specs → Joint table](./hardware_specs.md#joint-table).

## MIT-mode command convention

Every plugin (Robstride, Sito, MujocoSystem) computes torque as:

```
τ = K_p · (q_cmd − q) + K_d · (q̇_cmd − q̇) + τ_ff
```

Five command interfaces per joint: `position`, `velocity`, `effort`,
`stiffness`, `damping`. Three state interfaces: `position`, `velocity`,
`effort`. See [Concepts → MIT command surface](../concepts/mit_command_surface.md).

## Frequent failure modes (one-liners)

| Symptom | First thing to check |
|---|---|
| `ENOBUFS` / `Network is down` warnings | Motor power off → frames don't ACK → qdisc fills. Power the motors. |
| `/lite/joint_states` shows exactly 0.0 for every joint | Motors un-Enabled (no power, or Enable frame dropped). Check `/safety_status flags`. |
| Launch dies with "`joy_dev:=/dev/input/jsN` does not exist" | `enable_gamepad:=true` is the default and the bringup hard-fails when the resolved joystick path is missing. Plug a gamepad in, pass `joy_dev:=<actual path>` (the error message lists any other `/dev/input/js*` it found), or pass `enable_gamepad:=false`. |
| `mode_manager` rejects `LOAD_A`/`LOAD_B` from anywhere other than DAMPING | Send DAMP (`X`) first. See FSM table above. |
| `ros2 topic echo /safety_status` reports `flags ≠ 0` | Check [Concepts → Safety pipeline](../concepts/safety_pipeline.md) for the bit definitions. |

Full guidance: [Troubleshooting](./troubleshooting.md).
