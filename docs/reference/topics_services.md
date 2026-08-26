---
title: Topics & services
---

# Topics & services

Index of the ROS topics and services that `Humanoid Control` publishes,
subscribes, or serves. Use this page to find "who publishes X" or
"what topic carries Y".

## Topics

### Always-on (any bringup)

| Topic | Type | QoS | Publisher | Notes |
|---|---|---|---|---|
| `/lite/joint_states` | `sensor_msgs/JointState` | RELIABLE depth 10 | `joint_state_broadcaster` (remapped at bringup) | Position/velocity/effort in joint frame (post-calibration). Owner-prefixed — there is no global `/joint_states`. 50 Hz real, 200 Hz sim. |
| `/imu/data` | `sensor_msgs/Imu` | RELIABLE | IMU driver | Subscribed by `RLPolicyController` (in-process, for the `imu_*` observation terms). |
| `/robot_description` | `std_msgs/String` | RELIABLE TRANSIENT_LOCAL depth 1 | `robot_state_publisher` | URDF XML. Latched — subscribers can join any time. |
| `/tf`, `/tf_static` | `tf2_msgs/TFMessage` | RELIABLE | `robot_state_publisher` | Kinematic chain from `/lite/joint_states`. |
| `/clock` | `rosgraph_msgs/Clock` | RELIABLE | `mujoco_sim` (sim only) | Sim-time on the MuJoCo path. Every other node consumes when `use_sim_time:=true`. |

### Bringup-dependent

| Topic | Type | QoS | Publisher | When present |
|---|---|---|---|---|
| `/safety_status` | `humanoid_control_msgs/SafetyStatus` | RELIABLE TRANSIENT_LOCAL depth 1 | every hardware plugin | Per-bus (`humanoid_devices_robstride/can0`, `humanoid_devices_robstride/can1` for Lite). Published only on change. Telemetry — no automatic consumer now (native `fallback_controllers` handles faults; operator reacts to the rest). |
| `/standby_controller_a/state` | `humanoid_control_msgs/StandbyState` | RELIABLE TRANSIENT_LOCAL depth 1 | `humanoid_control/StandbyController` instance `standby_controller_a` (when active) | Pose A. Telemetry only — `is_finished` no longer gates anything. |
| `/standby_controller_b/state` | `humanoid_control_msgs/StandbyState` | RELIABLE TRANSIENT_LOCAL depth 1 | `humanoid_control/StandbyController` instance `standby_controller_b` (when active) | Pose B. Telemetry only. (Lite also spawns `standby_controller_y` → `/standby_controller_y/state`.) |
| `/joy` | `sensor_msgs/Joy` | SENSOR_DATA | `joy_node` | When `enable_gamepad:=true` (default). Consumed by `joy_teleop` (not `mode_manager`). The launch stops when `joy_device_id` is not connected. |

### Active-controller-dependent

| Topic | Type | QoS | Direction | When |
|---|---|---|---|---|
| `/remote_policy_controller/command` | `humanoid_control_msgs/MITCommand` | RELIABLE depth 4 | subscribed by `RemotePolicyController` | When `RemotePolicyController` is active. Published by a System 1/2 external-command source (gravity-comp runner today, VLA / manipulation later). Not used by the learned policies — those run in-process. |
| `/piano/key_state` | `std_msgs/Float32MultiArray` | RELIABLE KEEP_LAST(1) | sim: `pianist_policy/piano_state_bridge`; real: `pianist_policy/midi_keyboard_driver` | Piano runs. Live key state (0.0/1.0 per key). Consumed by the in-process `RLPolicyController` as the `key_pressed` extern observation term. |
| `/forward_mit_controller/commands` | `std_msgs/Float64MultiArray` | RELIABLE depth 10 | subscribed by upstream `forward_command_controller/MultiInterfaceForwardCommandController` | Used by `mit_slider_gui`. |

### `/parameter_events` and friends

Every node (controllers, joy_teleop, plugins) publishes the
standard ROS infrastructure topics:
- `/parameter_events`, `/rosout`
- `~/get_parameters`, `~/set_parameters`, etc. (per node)

These are conventional ROS — not specific to `Humanoid Control`. Mentioned
here so `ros2 topic list` output isn't confusing.

## Services

### Mode switching

There are **no** `/humanoid_control/mode/*` `std_srvs/Trigger` services anymore
— the `mode_manager` node that hosted them has been removed. Mode switching now
goes through the standard controller-manager service
`/controller_manager/switch_controller`
(`controller_manager_msgs/srv/SwitchController`), driven by `joy_teleop` from
the gamepad or by `ros2 control switch_controllers` on the command line. See
the controller_manager-side services below.

### controller_manager-side (under `/controller_manager`)

Standard `controller_manager` services. Useful ones:

| Service | Type | Purpose |
|---|---|---|
| `/controller_manager/list_controllers` | `controller_manager_msgs/ListControllers` | What's loaded, active state per controller |
| `/controller_manager/list_hardware_components` | `controller_manager_msgs/ListHardwareComponents` | Which `<ros2_control>` blocks are active |
| `/controller_manager/load_controller` | `controller_manager_msgs/LoadController` | Backing for `ros2 control load_controller` |
| `/controller_manager/switch_controller` | `controller_manager_msgs/SwitchController` | Backing for `ros2 control switch_controllers` |
| `/controller_manager/configure_controller` | `controller_manager_msgs/ConfigureController` | Force `on_configure` |

`joy_teleop` is a client of `/controller_manager/switch_controller` (each button
→ one activate + sibling deactivates, `BEST_EFFORT` strictness). You can call it
directly from `ros2 control` for operator-driven debug — see
[How-to → Switch without the FSM](../how_to/switch_controllers_manually.md).

### Per-node services (parameter handling)

Every node hosts the standard rclcpp parameter services:
- `~/get_parameters`, `~/set_parameters`, `~/list_parameters`, etc.

`rqt_reconfigure` is a generic frontend for these.

## QoS reference

Used in the tables above:

| QoS profile | Reliability | Durability | History | When |
|---|---|---|---|---|
| `RELIABLE` (default) | RELIABLE | VOLATILE | KEEP_LAST 10 | Most topics |
| `SENSOR_DATA` | BEST_EFFORT | VOLATILE | KEEP_LAST 5 | High-rate sensors — IMU, joy |
| `TRANSIENT_LOCAL` | RELIABLE | TRANSIENT_LOCAL | KEEP_LAST 1 | Latched — late subscribers see the most-recent value (URDF, SafetyStatus, StandbyState) |

If a publisher's QoS doesn't match a subscriber's, ROS may silently
drop messages. The TRANSIENT_LOCAL combo is the most common
mismatch source — subscribers must also request TRANSIENT_LOCAL
durability to receive the latched value.

## Inspecting at runtime

From a sourced workspace env (`cd humanoid_control_ws && pixi shell`):

```bash
# What's published right now?
ros2 topic list

# Who's publishing X?
ros2 topic info /lite/joint_states --verbose

# What's the QoS?
ros2 topic info /safety_status --verbose

# Recent rate
ros2 topic hz /lite/joint_states

# What service does X expose?
ros2 service list | grep controller_manager
ros2 service info /controller_manager/switch_controller
```

## See also

- [Reference → Messages](./messages.md) — full field schemas for the
  custom `humanoid_control_msgs` types.
- [Reference → Quick reference](./quick_reference.md) — common
  `ros2 topic echo` / `ros2 topic hz` invocations.
- [Concepts → Safety pipeline](../concepts/safety_pipeline.md) — what
  triggers a `/safety_status` publish.
