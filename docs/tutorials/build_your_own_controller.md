---
title: Build your own controller plugin
sidebar_position: 5
---

# Tutorial: Build your own controller plugin

Walk through the pieces of a `controller_interface::ControllerInterface`
plugin by building one yourself. We'll create `humanoid_control::HelloController`,
a minimal-but-real plugin that claims one joint's `position` command
interface and writes a sinusoidal target. By the end you'll know:

- The four lifecycle callbacks (`on_init`, `on_configure`,
  `on_activate`, `update`) and what goes in each.
- The pluginlib registration dance.
- How interface claiming works.
- How to load and activate your controller from the running stack.

This is **the** lesson for understanding why `humanoid_controllers` looks
the way it does.

## Time + materials

- 30 minutes
- A working workspace build
- Familiarity with C++ headers / CMakeLists (you can copy-paste, but
  you'll be more comfortable if you understand the includes)

## The plan

We'll add a new controller to `humanoid_controllers` (rather than a new
package, to skip the boilerplate). Five files change:

| File | What we do |
|---|---|
| `humanoid_controllers/include/humanoid_controllers/hello_controller.hpp` | New header — class definition |
| `humanoid_controllers/src/hello_controller.cpp` | New source — lifecycle bodies |
| `humanoid_controllers/humanoid_control_controllers_plugins.xml` | Register the new class with pluginlib |
| `humanoid_controllers/CMakeLists.txt` | Add the `.cpp` to the library |
| `humanoid_controllers/config/hello_controller.yaml` | Parameters at load time |

## Step 1 — Header

```cpp
// humanoid_controllers/include/humanoid_controllers/hello_controller.hpp
#pragma once

#include <string>
#include <vector>

#include <controller_interface/controller_interface.hpp>
#include <rclcpp/macros.hpp>

namespace humanoid_control
{

// Demo controller for the "build your own" tutorial. Claims one joint's
// `position` command interface and writes a sin wave around the joint's
// captured starting position.
class HelloController : public controller_interface::ControllerInterface
{
public:
  RCLCPP_SHARED_PTR_DEFINITIONS(HelloController)

  controller_interface::CallbackReturn on_init() override;
  controller_interface::CallbackReturn on_configure(
    const rclcpp_lifecycle::State & previous_state) override;
  controller_interface::CallbackReturn on_activate(
    const rclcpp_lifecycle::State & previous_state) override;

  controller_interface::InterfaceConfiguration command_interface_configuration() const override;
  controller_interface::InterfaceConfiguration state_interface_configuration() const override;

  controller_interface::return_type update(
    const rclcpp::Time & time, const rclcpp::Duration & period) override;

private:
  std::string joint_name_;
  double amplitude_{0.1};   // rad
  double frequency_{1.0};   // Hz
  double captured_position_{0.0};
  rclcpp::Time activate_time_;
};

}  // namespace humanoid_control
```

## Step 2 — Source

```cpp
// humanoid_controllers/src/hello_controller.cpp
#include "humanoid_controllers/hello_controller.hpp"

#include <cmath>
#include <pluginlib/class_list_macros.hpp>

#include "humanoid_control_common/loaned_interface_helpers.hpp"

namespace humanoid_control
{

using controller_interface::CallbackReturn;
using controller_interface::InterfaceConfiguration;
using controller_interface::interface_configuration_type;
using controller_interface::return_type;

CallbackReturn HelloController::on_init()
{
  // on_init: declare parameters that the user can override at load time.
  // No DDS / no interface access yet.
  try {
    auto_declare<std::string>("joint", "");
    auto_declare<double>("amplitude", 0.1);
    auto_declare<double>("frequency", 1.0);
  } catch (const std::exception & e) {
    fprintf(stderr, "HelloController::on_init: %s\n", e.what());
    return CallbackReturn::ERROR;
  }
  return CallbackReturn::SUCCESS;
}

CallbackReturn HelloController::on_configure(const rclcpp_lifecycle::State &)
{
  // on_configure: read parameters, set up pubs/subs (none here).
  // Validate that the config is sane.
  joint_name_ = get_node()->get_parameter("joint").as_string();
  if (joint_name_.empty()) {
    RCLCPP_ERROR(get_node()->get_logger(), "Parameter 'joint' must be set");
    return CallbackReturn::ERROR;
  }
  amplitude_ = get_node()->get_parameter("amplitude").as_double();
  frequency_ = get_node()->get_parameter("frequency").as_double();
  return CallbackReturn::SUCCESS;
}

CallbackReturn HelloController::on_activate(const rclcpp_lifecycle::State &)
{
  // on_activate: command interfaces are bound now. Capture initial state
  // so we have a baseline.
  captured_position_ = humanoid_control::get_state(state_interfaces_[0]);
  activate_time_ = get_node()->now();
  return CallbackReturn::SUCCESS;
}

InterfaceConfiguration HelloController::command_interface_configuration() const
{
  // What command interfaces does this controller claim?
  return InterfaceConfiguration{
    interface_configuration_type::INDIVIDUAL,
    {joint_name_ + "/position"},
  };
}

InterfaceConfiguration HelloController::state_interface_configuration() const
{
  // What state interfaces does this controller need to read?
  return InterfaceConfiguration{
    interface_configuration_type::INDIVIDUAL,
    {joint_name_ + "/position"},
  };
}

return_type HelloController::update(
  const rclcpp::Time & time, const rclcpp::Duration & /*period*/)
{
  // The hot path. Runs every tick. Must be RT-safe — no allocations,
  // no DDS, no exceptions across the boundary.
  const double t = (time - activate_time_).seconds();
  const double target = captured_position_ +
                        amplitude_ * std::sin(2.0 * M_PI * frequency_ * t);
  humanoid_control::set_cmd(command_interfaces_[0], target);
  return return_type::OK;
}

}  // namespace humanoid_control

PLUGINLIB_EXPORT_CLASS(humanoid_control::HelloController, controller_interface::ControllerInterface)
```

## Step 3 — Register with pluginlib

Add to `humanoid_controllers/humanoid_control_controllers_plugins.xml`:

```xml
<class
  name="humanoid_control/HelloController"
  type="humanoid_control::HelloController"
  base_class_type="controller_interface::ControllerInterface">
  <description>Demo controller: sin-wave around the joint's captured starting position. Used by docs/tutorials/build_your_own_controller.</description>
</class>
```

## Step 4 — CMakeLists

Add the new source to the existing library in
`humanoid_controllers/CMakeLists.txt`:

```cmake
add_library(${PROJECT_NAME} SHARED
  src/zero_torque_controller.cpp
  src/damping_controller.cpp
  src/standby_controller.cpp
  src/rl_policy_controller.cpp
  src/remote_policy_controller.cpp
  src/mit_joint_trajectory_controller.cpp
  src/hello_controller.cpp          # ← new
)
```

## Step 5 — Build

```bash
cd ~/humanoid_control_ws
pixi shell
colcon build --symlink-install --packages-select humanoid_controllers
```

If the build fails:
- Missing include → check `controller_interface/controller_interface.hpp` is included.
- `PLUGINLIB_EXPORT_CLASS` undefined → check `pluginlib/class_list_macros.hpp` is included.
- Plugin XML not found → check the plugin description file path in `CMakeLists`.

Verify pluginlib sees the new controller:

```bash
ros2 control list_controller_types | grep Hello
# humanoid_control/HelloController                            controller_interface::ControllerInterface
```

## Step 6 — Run it

```bash
# Bring up Lite with joy_teleop disabled so its button bindings don't
# switch controllers out from under our hand-loaded one:
ros2 launch humanoid_bringup_lite lite_mujoco.launch.py enable_joy_teleop:=false
```

In another terminal, load the controller via the CLI (inside
`pixi shell`):

```bash
ros2 control load_controller \
    --set-state inactive \
    --param-file <(cat <<EOF
hello_controller:
  ros__parameters:
    joint: left_shoulder_pitch
    amplitude: 0.2
    frequency: 0.5
EOF
) \
    hello_controller
```

(Or save the YAML and point `--param-file` at the file.)

Confirm it's loaded:

```bash
ros2 control list_controllers
# hello_controller        humanoid_control/HelloController        inactive
```

Now activate it — but first deactivate `zero_torque_controller` so
it isn't fighting over the same joint:

```bash
ros2 control switch_controllers \
    --deactivate zero_torque_controller \
    --activate   hello_controller
```

The left shoulder pitch should now sweep ±0.2 rad at 0.5 Hz. Watch
in the MuJoCo viewer.

## Step 7 — Shut down

```bash
ros2 control switch_controllers \
    --deactivate hello_controller \
    --activate   zero_torque_controller
```

Then `Ctrl+C` the launch.

## Key takeaways

| Concept | What you saw |
|---|---|
| Pluginlib registration | XML descriptor + `PLUGINLIB_EXPORT_CLASS` macro + CMake reference |
| Lifecycle | `on_init` (declare params) → `on_configure` (read params, set up) → `on_activate` (capture state) → `update` (hot path) |
| Interface claiming | Returned from `command_interface_configuration()` and `state_interface_configuration()` |
| State reading | `humanoid_control::get_state(state_interfaces_[i])` |
| Command writing | `humanoid_control::set_cmd(command_interfaces_[i], value)` |
| Mutual exclusion | Only one controller can claim a given interface — the controller_manager enforces this on `switch_controllers` |

## Where the existing controllers extend this pattern

| Controller | Distinct mechanism worth studying |
|---|---|
| `humanoid_control/ZeroTorqueController` | The minimal case — claims all 5 MIT interfaces, writes 0. Best baseline. |
| `humanoid_control/DampingController` | Captures state on activate; uses a YAML per-joint or scalar fallback. |
| `humanoid_control/StandbyController` | Interpolates its setpoint from the current measured joint positions to a target pose at constant PD (no gain ramp); publishes its own state topic. |
| `humanoid_control/RLPolicyController` | The in-process System 0 policy: preloads a `.mcap` motion reference and runs ONNX inference inside `update()`; observation packing + action mapping, all RT-safe. |
| `humanoid_control/RemotePolicyController` | The System 1/2 external-command ingress: subscribes to an `MITCommand` topic; `RealtimeBuffer` for the RT handoff; arrival-time-based stale-command policy. |

Read those in order — the complexity ramps up.

## See also

- [`ControllerInterface` API docs](https://control.ros.org/master/doc/api/classcontroller__interface_1_1ControllerInterface.html).
- [Reference → Controllers](../reference/controllers.md) — per-plugin parameters.
- [`humanoid_control_common/loaned_interface_helpers.hpp`](https://github.com/Berkeley-Humanoids/humanoid_control_ros2/blob/main/humanoid_control_common/include/humanoid_control_common/loaned_interface_helpers.hpp)
  — what `get_state` / `set_cmd` actually do (they wrap Jazzy's
  `[[nodiscard]]` migration helpers).
