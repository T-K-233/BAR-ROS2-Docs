---
title: MIT command surface
---

# MIT command surface

Every joint in Humanoid Control — Robstride, Sito, MujocoSystem, mock — exposes the
same **5 command interfaces** and **3 state interfaces**. This page
explains what those interfaces mean, how they combine into a single
torque, and why the same convention is used across silicon and
simulation.

![MIT-mode hybrid command](/img/diagrams/reference__hardware_specs__03.svg)

## The five command interfaces

| Interface | Symbol | Units | Meaning |
|---|---|---|---|
| `position`  | `q_cmd` | rad | Target joint position |
| `velocity`  | `q̇_cmd` | rad/s | Target / feedforward joint velocity |
| `effort`    | `τ_ff` | Nm | Feedforward torque |
| `stiffness` | `K_p` | Nm/rad | Position-error gain |
| `damping`   | `K_d` | Nm·s/rad | Velocity-error gain |

The actuator (or sim, or mock) reduces these to a single applied
torque every tick:

```
τ = K_p · (q_cmd − q) + K_d · (q̇_cmd − q̇) + τ_ff
```

The state side (read back at the same rate the actuator publishes) is
the same plus `effort` for sensed torque:

| State interface | Symbol | Units | Source |
|---|---|---|---|
| `position` | `q` | rad | encoder, calibrated to joint frame |
| `velocity` | `q̇` | rad/s | differentiated by firmware / sim |
| `effort`   | `τ` | Nm | sensed motor torque |

## Why all five

The point of the surface is that a single controller can address
**both classical and learned policies** without changing interface:

| Mode | What's nonzero | Equivalent classical regime |
|---|---|---|
| `q_cmd, K_p, K_d` (no `τ_ff`) | impedance / position control | PD around a setpoint |
| `q_cmd, q̇_cmd, K_p, K_d, τ_ff` | computed-torque control | inverse-dynamics + low-gain PD |
| `K_p=0, K_d>0` | velocity damping only | compliant fail-safe (our `DampingController`) |
| `K_p=0, K_d=0, τ_ff>0` | pure torque control | what a torque-based RL policy commands |
| `K_p=0, K_d=0, τ_ff=0` | zero torque | "alive but inert" (`ZeroTorqueController`) |

Controllers claim **whichever subset they need**; the others stay at
0 by default and contribute nothing. The actuator firmware doesn't
care which terms are nonzero — it just sums them.

## Why this convention specifically

The formula `τ = K_p·(q_cmd − q) + K_d·(q̇_cmd − q̇) + τ_ff` is the
**MIT mini-cheetah / Cheetah** convention, popularised on the
Robstride / T-Motor MIT-mode firmware and used by Berkeley Humanoids,
Hybrid Robotics' legged stacks, and most modern dynamic-legged-robot
projects. Three properties make it the right primitive:

1. **One formula across silicon and sim.** Robstride firmware computes
   it on the motor MCU; `mujoco_ros2_control::MujocoSystem` computes
   the same expression and applies it via `qfrc_applied`; our
   `humanoid_devices_robstride/RobstrideSystem` encodes the five fields straight
   into a wire frame. A controller written against this surface runs
   unchanged on silicon, MuJoCo, and `mock_components`.
2. **No mode-switching at the actuator.** "Switch from position control
   to torque control" stops being a state transition; you just stop
   setting `K_p` / `q_cmd` and start setting `τ_ff`. The actuator stays
   in the same control loop.
3. **Composability with RL.** Almost every RL policy that targets a
   legged robot today outputs joint targets (or deltas, or torques) on
   top of a fixed `K_p` / `K_d`. With the surface as-is, the policy is
   "just another controller" — same `update()` shape as a hand-tuned
   one.

## How it shows up in the URDF

The five command interfaces and three state interfaces are declared
per-joint inside each `<ros2_control>` block. From
`lite_description/robots/lite_dummy/xacro/lite_dummy.ros2_control.xacro`:

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
  <!-- per-joint <param>s here on the real-hardware path -->
</joint>
```

The interface **names** are not arbitrary. `stiffness` / `damping`
specifically are the names `mujoco_ros2_control::MujocoSystem` uses
(see its `HW_IF_STIFFNESS = "stiffness"` / `HW_IF_DAMPING = "damping"`
constants). Matching them verbatim is what makes the same URDF + the
same controller plug into both the sim and the silicon plugins
without rewriting.

## Reading the wire

For Robstride MIT-mode frames the five fields are encoded as 2-byte
unsigned values inside an 8-byte payload:

```
position  : 16 bits, signed, scaled to [-pos_lim, +pos_lim]   (model-dependent)
velocity  : 16 bits, signed, scaled to [-vel_lim, +vel_lim]
torque    : 16 bits, signed, scaled to [-trq_lim, +trq_lim]   (carried in extra_data of the CAN id)
kp        : 16 bits, unsigned, scaled to [0, kp_max]
kd        : 16 bits, unsigned, scaled to [0, kd_max]
```

Limits are model-specific (rs-00..rs-06); see
`humanoid_devices/humanoid_devices_robstride/include/humanoid_devices_robstride/robstride_protocol.hpp`.
`humanoid_devices_robstride/RobstrideSystem::write` does the scale-and-pack;
`read` reverses it.

## See also

- [Reference → Controllers](../reference/controllers.md) — which
  controller claims which interfaces.
- [Reference → Hardware specs → MIT-mode command convention](../reference/hardware_specs.md#mit-mode-command-convention)
  — short-form repeat of the formula.
- The protocol header in
  [`humanoid_devices_robstride/robstride_protocol.hpp`](https://github.com/Berkeley-Humanoids/humanoid_control_ros2/blob/main/humanoid_devices/humanoid_devices_robstride/include/humanoid_devices_robstride/robstride_protocol.hpp)
  is the source-of-truth for the wire encoding.
