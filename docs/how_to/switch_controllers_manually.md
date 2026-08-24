---
title: Switch controllers without the FSM
---

# Switch controllers without the FSM

There is no mode-arbitration node anymore — a control-mode change is
just a `switch_controller` call on the `controller_manager`. The
gamepad's `joy_teleop` node maps buttons directly to those calls; this
how-to is the CLI equivalent, and the primary path on a dev or headless
host without a gamepad.

:::note[No gamepad? This is your mode-switch path.]
Humanoid Control ships **no keyboard control** — the `joy_teleop` node
reacts to a gamepad (`/joy`) only. On a dev or headless host without one,
the `ros2 control` calls on this page **are** the supported way to drive
modes by hand.
:::

## Why switch by hand

| Use case | Why the CLI |
|---|---|
| Headless / dev host | No gamepad attached, so `/joy` never arrives — the CLI is the only mode-switch input. |
| Verifying a new controller plugin | Load + activate it directly by name, no gamepad binding required. |
| Recording sysid traces | Scripted switches are exactly reproducible run to run. |
| Debugging a controller's `on_activate` | Direct control + log inspection, one switch at a time. |

The gamepad and the CLI hit the **same** `switch_controller` service.
`joy_teleop` only issues a switch when a button is pressed and keeps no
state of its own, so background CLI calls never fight it.

## Turn off the gamepad layer (optional)

You don't need to disable anything — CLI switches work whether or not
`joy_teleop` is running. If you'd rather drop the gamepad layer
entirely (no button bindings on `/joy`), pass `enable_joy_teleop:=false`:

```bash
ros2 launch humanoid_bringup_lite lite_real.launch.py enable_joy_teleop:=false
```

Either way `zero_torque_controller` comes up active (the spawner sets it
active) and the other controllers load inactive. Nothing watches
`/safety_status` to switch modes for you — the operator drives every
switch.

## Common switches

Switching is **flat**: any controller can be activated from any state,
and each switch just deactivates the current mode and activates the new
one (`--strict` optional; the gamepad uses best-effort). The examples
below are ordered for a typical bring-up, but you can go directly
between any two — e.g. `zero_torque_controller` straight to
`rl_policy_controller`.

The commands below are interactive `ros2 control` / `ros2 topic`
calls — open a second terminal and `pixi shell` into the workspace so
`ros2` is on PATH:

```bash
cd humanoid_control_ws
pixi shell
```

### ZERO_TORQUE → DAMPING

```bash
ros2 control switch_controllers \
    --deactivate zero_torque_controller \
    --activate   damping_controller
```

The robot becomes "compliant against velocity but no position holding".
Pushing the arm by hand will move it; let go and it stops without
oscillating.

### DAMPING → STANDBY

STANDBY has three poses, each a separately spawned instance of the same
plugin: `standby_controller_a` (Pose A), `standby_controller_b`
(Pose B), and `standby_controller_y` (Pose Y) — the gamepad's `L1+A`,
`L1+B`, and `L1+Y`. Activate whichever pose you want:

```bash
ros2 control switch_controllers \
    --deactivate damping_controller \
    --activate   standby_controller_a
```

Use `--activate standby_controller_b` (or `_y`) instead for the other
poses.

**The motors will move.** Standby holds the target `K_p` / `K_d` from
t=0 — there is **no gain ramp** — and seeds its setpoint to the
**current measured** joint positions, then interpolates that setpoint to
the pose's target. Because it starts from where the joints already are,
it's safe to enter from any state with no jump; the arms still travel to
the target pose over ~4 seconds, so support them or keep the workspace
clear.

Watch the state topic for the pose you activated (one per instance) for
`is_finished: true`:

```bash
ros2 topic echo /standby_controller_a/state
```

### STANDBY → REMOTE (or LOCOMOTION)

```bash
ros2 control switch_controllers \
    --deactivate standby_controller_a \
    --activate   remote_policy_controller
```

(Deactivate whichever standby instance is active —
`standby_controller_a`, `_b`, or `_y`. You can also enter REMOTE
directly from any other mode.)

`remote_policy_controller` (`humanoid_control/RemotePolicyController`) is the
**System 1/2 external-command ingress**: it immediately starts looking
for `MITCommand` on `/remote_policy_controller/command`. Without a
publisher it'll trip its stale-command policy (`passive` by default
→ a damped hold: zero stiffness, high damping like DAMPING, holding
live position) within 100 ms. To use this for real, start a
non-real-time `MITCommand` source first — gravity compensation
(`Lite-Gravity-Compensation`) today, VLA / manipulation later. This
controller is **not** fed by any learned policy; learned policies run
in-process in `rl_policy_controller`.

`rl_policy_controller` (`humanoid_control/RLPolicyController`) is **not** spawned by
`lite_real.launch.py` — it is loaded *inactive* by the prepare→spawn
[policy launch](./promote_python_to_cpp.md)
(`ros2 launch humanoid_control_policy lite_policy.launch.py checkpoint_file:=<path>`),
which runs `prepare` to resolve the ONNX + `.mcap` motion bag and emit
the parameter overlay. Once that launch has spawned it, you can activate
it by hand the same way as below.

### Anything → ZERO_TORQUE (always end here)

```bash
ros2 control switch_controllers \
    --deactivate <whatever_is_active> \
    --activate   zero_torque_controller
```

Before `Ctrl+C`-ing the launch, transition back to `zero_torque`.
The plugin's `on_deactivate` will send Disable to every motor when
the launch tears down, but landing at `zero_torque` first means
there's no risk of a non-zero command in flight at the moment of
shutdown.

## Inspecting state

```bash
# Which controllers are loaded, and which are active?
ros2 control list_controllers
# Expected after the first switch:
#   damping_controller        humanoid_control/DampingController        active
#   zero_torque_controller    humanoid_control/ZeroTorqueController     inactive
#   joint_state_broadcaster   joint_state_broadcaster/...  active
#   standby_controller_a      humanoid_control/StandbyController        inactive
#   standby_controller_b      humanoid_control/StandbyController        inactive
#   standby_controller_y      humanoid_control/StandbyController        inactive
#   remote_policy_controller  humanoid_control/RemotePolicyController   inactive

# What hardware components are up?
ros2 control list_hardware_components
# Expected for Lite:
#   LiteLeftArm   active
#   LiteRightArm  active

# What interfaces is the active controller claiming?
ros2 control list_controllers --verbose
```

## Useful one-liners

```bash
# Quick switch macro (drop into your bashrc)
ros2cs () {
    ros2 control switch_controllers --deactivate "$1" --activate "$2"
}
ros2cs zero_torque_controller damping_controller

# Force a strict switch (fail if either controller is in the wrong state)
ros2 control switch_controllers \
    --deactivate damping_controller \
    --activate   standby_controller_a \
    --strict
```

## Gamepad vs. CLI

Both paths call the same `switch_controller` service; neither gates or
orders the switch.

| | Gamepad (`joy_teleop`) | CLI (`ros2 control`) |
|---|---|---|
| Trigger | Button press | You type the command |
| Backend | `switch_controller`, best-effort | `switch_controller` (add `--strict` if you want) |
| Ordering / gating | None — any button, any state | None — any switch, any state |
| Which mode is active | `ros2 control list_controllers` | same |

There are **no FSM gates and no auto-DAMP** anymore. Safety comes from
two places: the operator (switch to STOP with `BACK` / `zero_torque` or
DAMP with `X` / `damping`, on the gamepad or the CLI), and each mode
controller's native `fallback_controllers` — a controller whose
`update()` errors is deactivated by the controller_manager, which then
activates its `damping_controller` fallback automatically. See
[Recover from a fault](./recover_from_fault.md).

## See also

- [The five control modes](../concepts/five_mode_fsm.md)
- [First real-hardware bringup](./first_real_bringup.md)
- [Recover from a fault](./recover_from_fault.md)
- [Reference → Controllers](../reference/controllers.md)
