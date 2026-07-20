---
title: Manual / debug controllers
---

# Manual / debug controllers

A short reference of the **non-mode** controllers — the ones the
operator activates by hand for testing, tuning, or debug. These
controllers aren't in the `joy_teleop` gamepad switch set and
aren't part of the production safety loop.

For the mode controllers (`zero_torque`, `damping`, `standby`,
`rl_policy`, `remote_policy`) see [Controllers](./controllers.md).

## When to reach for these

| Use case | Reach for |
|---|---|
| Tune the K_p / K_d for one joint interactively | `mit_slider_gui` + `forward_command_controller/MultiInterfaceForwardCommandController` |
| Drive a trajectory from a script without writing custom plugin code | `joint_trajectory_controller` (stock) bound to the `position` interface only |
| Manually exercise one or two joints from the CLI | `forward_command_controller` claiming the target interfaces |
| Test a new controller plugin you wrote | (your plugin) — see [Tutorials → Build your own controller](../tutorials/build_your_own_controller.md) |

All of these compete with the mode controllers for the same command
interfaces. Activate them with `enable_joy_teleop:=false` or
explicitly deactivate the mode controller (typically `zero_torque`)
first.

## `forward_command_controller/MultiInterfaceForwardCommandController`

Upstream from `ros2_controllers`. Claims **multiple interfaces on a
single joint**, forwarded from one `Float64MultiArray` topic. The
slider GUI sits on top of this.

```yaml
forward_mit_controller:
  ros__parameters:
    joint: actuator_1
    interface_names:
      - position
      - velocity
      - effort
      - stiffness
      - damping
```

Subscribes to `~/commands` (`std_msgs/Float64MultiArray`). The array
length must match `interface_names`'s length; each element goes
straight to the matching command interface in order.

The single-actuator bringup
(`humanoid_devices_robstride/single_robstride_gui.launch.py`) is the canonical
example.

## `joint_trajectory_controller` (stock ros2_controllers)

For multi-joint trajectory replay. Claims `position` (or `position +
velocity` for feedforward) per joint, accepts a
`trajectory_msgs/JointTrajectory` on `~/joint_trajectory` and the
matching `~/follow_joint_trajectory` action.

**Useful gotcha**: by default JTC only claims `position`. With the
MIT-mode plugins, you need a separate way to set non-zero
`stiffness`/`damping` — otherwise the motor receives MIT(pos, 0, 0,
0, 0), computes `τ = 0·err + 0·erṙ + 0 = 0`, and doesn't move.

The qiayuanl-style fix is to pair JTC with a
`forward_command_controller` that claims `stiffness`/`damping` on
the same joints and publishes them once via `ros2 topic pub
--once`. See `mujoco_ros2_control_demos/config/cartpole_controller_position.yaml`
for the upstream pattern.

We don't bundle a YAML for this in the project — the
`StandbyController` mode covers the production trajectory case
end-to-end. Drop in stock JTC for one-off scripted tests.

## `humanoid_control/MITJointTrajectoryController` (project-local)

Custom controller that **owns the full 5-interface MIT surface**
and accepts trajectories. Useful when you want the rqt-driven
trajectory UX without compositional `forward_command_controller`
sidecars.

```yaml
mit_joint_trajectory_controller:
  ros__parameters:
    joints: [...]
    kp: 2.0          # scalar applied to every joint
    kd: 0.5
    default_segment_duration_s: 1.0
```

Subscribes to `~/joint_trajectory` (`trajectory_msgs/JointTrajectory`)
and writes all 5 MIT fields every tick. Scalar `kp` / `kd` (no
per-joint array) keeps the config simple for ad-hoc tests; for
production use, the mode controllers are still the right home.

Not in the default spawner batch; load it manually (inside
`pixi shell`):

```bash
ros2 control load_controller \
    --set-state inactive \
    --param-file <path/to/yaml> \
    mit_joint_trajectory_controller

ros2 control switch_controllers \
    --deactivate zero_torque_controller \
    --activate   mit_joint_trajectory_controller
```

`rqt_joint_trajectory_controller`'s slider GUI **won't auto-discover
this** — it filters by upstream class name. Use `rqt_publisher` or
a one-shot `ros2 topic pub` to drive it.

## Hand-loading a controller (any of the above)

The standard flow (drop into `pixi shell` first so `ros2` is on PATH):

```bash
cd humanoid_control_ws && pixi shell

# 1. Make sure the controller TYPE is registered with pluginlib
ros2 control list_controller_types | grep <ClassName>

# 2. Load + configure with a parameter file
ros2 control load_controller \
    --set-state inactive \
    --param-file <path/to/yaml> \
    <controller_name>

# 3. Activate (deactivating whatever holds the same interfaces)
ros2 control switch_controllers \
    --deactivate <conflicting_controller> \
    --activate   <controller_name>
```

If `load_controller` reports `controller is in state 'unconfigured'`,
`on_configure` failed — read the launch log. Common causes are
missing required parameters or invalid types.

If `switch_controllers` reports a claim conflict, two controllers
want the same interface. Active-set the deactivate list first.

## See also

- [Tutorials → Build your own controller plugin](../tutorials/build_your_own_controller.md)
  — for when you write your own.
- [How-to → Drive a single joint with mit_slider_gui](../how_to/mit_slider_gui.md)
  — operator-side workflow for the slider GUI.
- [How-to → Switch without the FSM](../how_to/switch_controllers_manually.md)
  — driving controllers directly with `ros2 control switch_controllers`.
- [Reference → Controllers](./controllers.md) — the mode controllers.
