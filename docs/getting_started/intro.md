# Introduction

`Humanoid Control` is the unified low-level control stack for the **Berkeley Architecture
Research (Humanoid Control)** humanoid robots. It runs on **ROS 2 Jazzy under PREEMPT_RT**
(shipped via the [RoboStack](https://robostack.github.io) conda channel and
pixi, no system-wide ROS install required) and targets two robots with **as
much shared code as possible**.

Task-specific packages (piano playing, etc.) ship from sibling repos
that depend on `Humanoid Control` — see [Packages reference](../reference/packages.md)
for the split. Throughout the rest of the docs, runtime commands are
shown in canonical `ros2 launch …` / `ros2 run …` form; if you prefer
shorter aliases, the workspace also ships a `pixi run …` shortcut
layer documented on
[How-to → Workspace shortcuts with pixi](../how_to/use_pixi_tasks.md).

The two robots:

- **Lite** — a bimanual humanoid with **Robstride actuators on two SocketCAN
  buses** (CAN-to-USB), one bus per arm.
- **Prime** — a bimanual humanoid with **eRob actuators over EtherCAT** and
  **Sito actuators over SocketCAN**, running concurrently. The EtherCAT side is
  driven by the third-party
  [`ethercat_driver_ros2`](https://github.com/ICube-Robotics/ethercat_driver_ros2)
  (ICube Robotics), built on the IgH EtherLAB master.

> **The headline**: identical controllers, message schemas, simulation tooling,
> and bringup launches across both robots. Robot differences live entirely in
> URDF and hardware-component selection.

## What problem does this stack solve?

Humanoid control codebases historically split along a robot-by-robot,
hardware-by-hardware axis: separate plugins for each actuator family, separate
launch files per task, separate observation pipelines for sim vs. silicon. The
result is N × M code paths, where N is robots and M is tasks.

`Humanoid Control` factors the axes orthogonally:

| Axis | Where the variation lives |
|---|---|
| Robot (Lite / Prime) | URDF + which `<ros2_control>` `<plugin>` is selected |
| Hardware tier (mock / sim / real) | two xacro args (`use_mock_hardware` / `sim_mujoco`) |
| Task (tracking / piano / locomotion) | the `.onnx` + `.mcap` loaded into the one in-process `RLPolicyController` (the ONNX `task_type` selects observation terms) |

Everything else is shared. Every learned policy is **System 0**: it
runs in-process in C++ `RLPolicyController` inside the real-time
`ros2_control` cycle — there is no separate policy process.

## System at a glance

![System at a glance](/img/diagrams/getting_started__intro__01.svg)

The two CAN buses on Lite are a **physical** split (one CAN-to-USB adapter per
arm), surfaced as **two `<ros2_control>` blocks** on the real-hardware path:
`LiteLeftArm` claims CAN ids 11..17 on `can_interface_left`, `LiteRightArm`
claims 21..27 on `can_interface_right`. The controller_manager runs both
plugin instances concurrently and exposes a single flat 14-joint list to
controllers — they don't see the split. Prime adds a third path through
`ethercat_driver_ros2` for the eRob side.

## How the project is organized

A single git repo at `Berkeley-Humanoids/humanoid_control_ros2`, a flat collection of ROS 2 packages
(franka_ros2 / Universal_Robots_ROS2_Driver pattern):

![Package organization](/img/diagrams/getting_started__intro__02.svg)

Notice that **`humanoid_controllers`, `humanoid_control_msgs`, and `humanoid_control_policy` have no
robot-specific code** — everything robot-specific lives in `humanoid_control_description_*`
or `humanoid_bringup_*`.

## Design rationale (one-paragraph version)

`ros2_control` is the integration spine. Every joint exposes **3 state
interfaces** (`position`, `velocity`, `effort`) and **5 command interfaces**
(`position`, `velocity`, `effort`, `stiffness`, `damping`) — the **MIT-mode
hybrid command** convention used by Cheetah, MIT Mini Cheetah, and the Berkeley
Humanoids deployments. The actuator (or sim, or mock) computes torque as

```
tau = K_p (q_cmd - q) + K_d (q_dot_cmd - q_dot) + tau_ff
```

This formula is identical in our Robstride firmware, in
`mujoco_ros2_control::MujocoSystem`, and in any controller we write — so the
same `update()` body works against silicon, MuJoCo, and `mock_components`. See
[Architecture](../concepts/architecture.md) for the full ros2_control flow.

## Reference materials

The architectural choices in this stack draw heavily on prior work. The
project's `AGENTS.md` (kept project-local, not in the git repo) cites the full
list; the most influential are:

- **[rm_control](https://github.com/rm-controls/rm_control)** — package
  decomposition pattern and `industrial_ci` workflow.
- **[legged_control2](https://qiayuanl.github.io/legged_control2_doc/overview.html)**
  — two-tier hardware factoring (bus library / per-actuator-family plugin)
  that we mirror for `humanoid_drivers_socketcan` / `humanoid_devices_robstride` / `humanoid_devices_sito`.
- **[mujoco_ros2_control](https://github.com/qiayuanl/mujoco_ros2_control)** —
  the MuJoCo ↔ ros2_control bridge whose `MujocoSystem` plugin we consume.
- **[franka_ros2](https://github.com/frankarobotics/franka_ros2)** — the flat
  package-collection layout this repo follows.
- **[Universal_Robots_ROS2_Driver](https://github.com/UniversalRobots/Universal_Robots_ROS2_Driver)**
  — gold-standard `ros2_control` hardware integration. The
  `Universal_Robots_Client_Library` / `ur_robot_driver` split mirrors our
  `humanoid_drivers_socketcan` / `humanoid_devices_robstride` split.

## Next

- [Hardware specifications](../reference/hardware_specs.md) — joint counts,
  effort limits, transport details for Lite and Prime.
- [Architecture](../concepts/architecture.md) — ros2_control flow, the five
  control modes (flat joy_teleop switching), and the in-process System 0 policy tier.
- [Installation](./installation.md) — install the prebuilt packages from the
  `berkeley-humanoids` channel in ~2 minutes, or build from source.