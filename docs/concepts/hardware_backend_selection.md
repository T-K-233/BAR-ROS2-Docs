---
title: Hardware backend selection
---

# Hardware backend selection

A description package has to describe one robot that runs on three different plants: real
actuators on a bus, a physics simulator, and nothing at all. This page records how
`lite_description` chooses between them, and why it is shaped the way it is.

## The three backends

| Backend | `ros2_control` plugin | What it is for |
|---|---|---|
| real | `humanoid_devices_robstride/RobstrideSystem` | RobStride actuators over SocketCAN |
| MuJoCo | `mujoco_ros2_control/MujocoSystem` | the training and deployment simulator |
| mock | `mock_components/GenericSystem` | no hardware and no simulator |

The mock backend mirrors each command straight back to its state interface. It runs
nothing physical, which makes it the path for exercising launch files, controller
configuration and CI without a robot or a simulator on hand.

## Two boolean args, real as the fallback

The generated `<robot>.urdf.xacro` declares one boolean per non-real backend:

| `sim_mujoco` | `use_mock_hardware` | Backend |
|---|---|---|
| `false` | `false` | real |
| `false` | `true` | mock |
| `true` | any | MuJoCo |

`sim_mujoco` wins over `use_mock_hardware`.

This follows the [Universal Robots description](https://github.com/UniversalRobots/Universal_Robots_ROS2_Description/blob/ros2/urdf/ur.ros2_control.xacro),
which declares `use_mock_hardware` alongside one boolean per simulator (`sim_gazebo`,
`sim_ignition`) and treats real hardware as the `xacro:unless` fallback. The
[HEBI examples](https://github.com/HebiRobotics/hebi_ros2_examples) use the same shape.
We name our simulator boolean `sim_mujoco` for the same reason those name theirs after
Gazebo: a second simulator would be a second boolean, not a redefinition of the first.

### Why the names changed

Both args were renamed in the `lite_description` cleanup:

- `use_fake_hardware` became `use_mock_hardware`. `fake_components` was renamed
  `mock_components` in ROS 2 Iron, and `fake_sensor_commands` became
  `mock_sensor_commands` with it. `ros2_control_demos` and the UR driver both moved to
  `use_mock_hardware`. `franka_ros2` kept the old spelling, which is why our generator
  originally cited it.
- `use_sim` became `sim_mujoco`. `use_sim` is not a ros2_control convention at all. It also
  reads as a near-synonym of `use_sim_time`, which is a standard ROS 2 **node parameter
  about the clock** and has nothing to do with choosing a hardware plugin. Our launch
  files set both, a few lines apart, so the collision was real.

### The alternative we did not take

A single enum arg, along the lines of MoveIt Setup Assistant's
`ros2_control_hardware_type`, would make the three backends mutually exclusive by
construction. That would delete the `sim_mujoco` wins over `use_mock_hardware`
precedence rule, which today has to be written down rather than enforced.

We stayed with two booleans because the per-simulator-boolean pattern is the more common
one in description packages specifically, and because it keeps the diff to downstream
launch files small. The cost is that one of the four combinations,
`sim_mujoco:=true use_mock_hardware:=true`, has no distinct meaning. Launch files on the
MuJoCo path therefore pass `sim_mujoco:=true` alone and leave the mock arg at its default.

## The switches never reach the joints

Joint macros are backend-agnostic. Every `<joint>` carries its full hardware params
(`can_id`, `model`, `direction`, the limits, and the four-bar geometry where there is one)
no matter which backend is selected:

```xml
<xacro:macro name="lite_biped_joint"
             params="name can_id model direction lower_limit upper_limit torque_limit
                     current_limit">
  <joint name="${name}">
    <command_interface name="position"/>
    <!-- ... -->
    <param name="can_id">${can_id}</param>
    <!-- ... -->
  </joint>
</xacro:macro>
```

This is safe because every backend ignores the params it does not recognise.
`MujocoSystem` reads only `mimic` and `multiplier` from a joint's params
(`mujoco_ros2_control/src/mujoco_system.cpp`). `mock_components/GenericSystem` collects
the rest and never validates them.

Earlier revisions wrapped those params in a `xacro:unless` guard on the two switches.
That forced both switches to be threaded as parameters through every group macro and
every joint call. Removing the guard cost nothing and left `sim_mujoco` alive in exactly
two places: the `<hardware>` plugin choice, and the base-IMU `<sensor>` element, which
only MuJoCo can back.

## One block per bus on the real path

The mock and MuJoCo backends emit a single combined `<ros2_control>` block holding every
joint. Real hardware cannot do that: each physical CAN bus needs its own hardware
component, so the real path emits one `<ros2_control name="..." type="system">` per bus,
plus a separate `type="sensor"` block for the base IMU where the variant has one.

The controller_manager runs those blocks concurrently and still exposes one flat joint
list, so controllers see the same interface surface on every backend.

```
lite_biped, real   -> LiteBipedLeftLeg (7 joints), LiteBipedRightLeg (7), LiteBipedIMU (1 sensor)
lite_biped, sim    -> LiteBipedHardware (14 joints, 1 sensor)
lite_biped, mock   -> LiteBipedHardware (14 joints, 0 sensors)
```

## See also

- [Reference → URDF / xacro args](../reference/urdf_args.md) — the full arg and param surface.
- [Concepts → MIT command surface](./mit_command_surface.md) — why the interface set is what it is.
- [Reference → Launch args](../reference/launch_args.md) — how the launch files feed these args.
