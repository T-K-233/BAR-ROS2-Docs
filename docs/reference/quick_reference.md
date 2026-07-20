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
scripts are on `PATH`. Looking for the workspace tasks (`pixi run sim`,
`pixi run build`, `pixi run ping-bus`, …)?  See
[How-to → Workspace commands](../how_to/use_pixi_tasks.md).

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
# Real Lite — both buses, two ros2_control blocks, gamepad + joy_teleop
ros2 launch humanoid_bringup_lite real.launch.py

# Real Lite, no gamepad attached (switch controllers via ros2 control switch_controllers)
ros2 launch humanoid_bringup_lite real.launch.py enable_gamepad:=false

# Gamepad enumerated as js1 (multiple controllers plugged into the Jetson)
ros2 launch humanoid_bringup_lite real.launch.py joy_dev:=/dev/input/js1

# Real Lite, no joy button switching (raw debug / calibration)
ros2 launch humanoid_bringup_lite real.launch.py enable_joy_teleop:=false
```

`real.launch.py` boots the real-time control plane only — visualisers
live on the operator workstation; the in-process policy is prepared and
loaded on the robot below.

### Robot onboard computer (prepare + load a policy)

```bash
# Prepare + load the in-process tracking policy (Humanoid Control → humanoid_control_policy):
# runs `prepare` (ONNX → .mcap + overlay), then loads rl_policy_controller
# inactive. Activate it with R1+A (joy_teleop) or:
#   ros2 control switch_controllers --activate rl_policy_controller --deactivate <current>

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

These are the workspace utility tasks — one-line wrappers over the
`ros2 run humanoid_devices_robstride …` invocations listed in
[Diagnostics and utility commands](./cli_tools.md).

```bash
# Scan an ID range; read-only, no Enable
pixi run scan-bus --iface can0 --scan-to 32
pixi run scan-bus --iface can1 --scan-to 32

# One-shot GetDeviceId / OperationStatus probe
pixi run ping-bus --iface can0 --id 11

# Per-joint slider window (forward_command_controller frontend; no task)
ros2 run humanoid_devices_robstride mit_slider_gui

# Live URDF + /lite/joint_states viewer — pixi run viz wraps this launch
ros2 launch humanoid_bringup_lite viz.launch.py                  # viser, browser at :8080
ros2 launch humanoid_bringup_lite viz.launch.py viewer:=rerun    # native rerun window

# Single-machine sim/dev shortcuts for the raw viewer executables (no task)
ros2 run humanoid_bringup_lite viser_viz
ros2 run humanoid_bringup_lite rerun_viz
```

## Mode-FSM gamepad bindings (Xbox layout)

The stock `joy_teleop` node (from `teleop_tools`) maps each button
**directly** to `/controller_manager/switch_controller` — there is no FSM.
Every binding activates one controller and deactivates its siblings
(flat, `BEST_EFFORT`); any binding works from any state, with no gating
and no ordering.

| Buttons | Activates |
|---|---|
| `X` | `damping_controller` |
| `L1 + A` | `standby_controller_a` |
| `L1 + B` | `standby_controller_b` |
| `L1 + Y` | `standby_controller_y` |
| `R1 + A` | `rl_policy_controller` (locomotion) |
| `R1 + B` | `remote_policy_controller` |
| `BACK` | `zero_torque_controller` (STOP) |

`BACK` selects `zero_torque_controller` — it does **not** shut the process
down; CAN Disable still happens on `Ctrl+C` via the hardware
`on_deactivate`. Pose and policy are independent, and every transition is
allowed from every state — from any standby pose (or any other state)
`R1+A` → locomotion or `R1+B` → REMOTE, and you can switch directly
between poses. See
[Manual controller switching](#manual-controller-switching-no-fsm) for the
equivalent `ros2 control` calls.

## Manual controller switching (no FSM)

These are interactive `ros2 control` calls:

```bash
# ZERO_TORQUE → DAMPING
ros2 control switch_controllers \
    --deactivate zero_torque_controller \
    --activate   damping_controller

# any state → STANDBY Pose A (interpolates from the measured pose toward the
# Pose A target, constant PD from t=0, no stiffness ramp — safe from any state;
# standby_controller_b / _y are the other poses)
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
| `/safety_status` | `humanoid_control_msgs/SafetyStatus` | on-change, latched | TRANSIENT_LOCAL; `source` field per bus |
| `/standby_controller_a/state` | `humanoid_control_msgs/StandbyState` | active-only | TRANSIENT_LOCAL; Pose A |
| `/standby_controller_b/state` | `humanoid_control_msgs/StandbyState` | active-only | TRANSIENT_LOCAL; Pose B |
| `/standby_controller_y/state` | `humanoid_control_msgs/StandbyState` | active-only | TRANSIENT_LOCAL; Pose Y |
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

# Switch controllers without a gamepad (any transition, from any state)
ros2 control switch_controllers --activate damping_controller --deactivate zero_torque_controller
ros2 control switch_controllers --activate standby_controller_a --deactivate damping_controller

# Fake a System 1/2 MITCommand publish (when remote_policy_controller is active in MuJoCo)
ros2 topic pub --once /remote_policy_controller/command \
    humanoid_control_msgs/msg/MITCommand "{header: {stamp: now}, joint_names: [...], ...}"
```

## Services for FSM transitions

The `/humanoid_control/mode/*` `std_srvs/Trigger` services were **removed**
along with the FSM. Switch controllers directly instead — every transition
is allowed from every state (activate one controller, deactivate the
current one):

| Former intent | Command |
|---|---|
| DAMP | `ros2 control switch_controllers --activate damping_controller --deactivate <current>` |
| STANDBY A | `ros2 control switch_controllers --activate standby_controller_a --deactivate <current>` |
| STANDBY B | `ros2 control switch_controllers --activate standby_controller_b --deactivate <current>` |
| STANDBY Y | `ros2 control switch_controllers --activate standby_controller_y --deactivate <current>` |
| LOCOMOTION | `ros2 control switch_controllers --activate rl_policy_controller --deactivate <current>` |
| REMOTE | `ros2 control switch_controllers --activate remote_policy_controller --deactivate <current>` |
| STOP | `ros2 control switch_controllers --activate zero_torque_controller --deactivate <current>` |

The gamepad does exactly this via `joy_teleop`.

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
| A gamepad button doesn't switch the controller | Check `joy_teleop` is running and the target controller is loaded; read the active one with `ros2 control list_controllers`. |
| `ros2 topic echo /safety_status` reports `flags ≠ 0` | Check [Concepts → Safety pipeline](../concepts/safety_pipeline.md) for the bit definitions. |

Full guidance: [Troubleshooting](./troubleshooting.md).
