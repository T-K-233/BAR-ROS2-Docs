---
title: Switch controllers without the FSM
---

# Switch controllers without the FSM

`mode_manager` is the production path for changing controllers, but
sometimes you want **raw control** — debugging, calibration, scripted
tests, or just verifying the underlying controller_manager service.
This how-to walks the mode FSM via direct `ros2 control` calls.

:::note[No gamepad? This is your mode-switch path.]
Humanoid Control ships **no keyboard control** for the FSM — `mode_manager` reacts to a
gamepad (`/joy`) only. On a dev or headless host without one, the
`ros2 control` calls on this page **are** the supported way to drive modes
by hand. (There used to be a planned `termios` keyboard reader; it was
dropped in favour of this CLI path.)
:::

## Why bypass mode_manager

| Use case | Why FSM is in the way |
|---|---|
| Calibration | The FSM auto-DAMPs on safety events; sometimes you want to manually drive state through faults. |
| Verifying a new controller plugin | You want to load + activate it directly, not register it as an FSM mode. |
| Recording sysid traces | The FSM transitions add unmeasurable delay; manual switches are more reproducible. |
| Debugging a controller's `on_activate` | Direct control + log inspection without the FSM's `request_mode` retry chatter. |

The FSM doesn't enforce its rules at the controller_manager layer —
the controller_manager just sees `switch_controller` service calls.
So you can call them directly without any FSM in the loop.

## Disable the FSM in the launch

Easiest: pass `enable_mode_manager:=false` so `mode_manager` isn't
spawned at all:

```bash
ros2 launch humanoid_bringup_lite real.launch.py enable_mode_manager:=false
```

Now `zero_torque_controller` is active (the spawner set it active),
and the four other controllers are loaded as inactive. No FSM watches
`/safety_status`, no `/joy` is required. The operator drives every
transition.

## The four basic transitions

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

STANDBY has two poses, each a separately spawned instance of the same
plugin: `standby_controller_a` (Pose A) and `standby_controller_b`
(Pose B). Activate whichever pose you want:

```bash
ros2 control switch_controllers \
    --deactivate damping_controller \
    --activate   standby_controller_a
```

Use `--activate standby_controller_b` instead for Pose B.

**The motors will move.** Standby ramps `K_p` / `K_d` from 0 to the
target gains during segment 0, then interpolates to the piano-ready
pose during segment 1. Total runtime ~4 seconds. Support the arms or
have a clear workspace.

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
`standby_controller_a` or `standby_controller_b`.)

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
`real.launch.py` — it is loaded *inactive* by the prepare→spawn
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
# Expected after first transition:
#   damping_controller        humanoid_control/DampingController        active
#   zero_torque_controller    humanoid_control/ZeroTorqueController     inactive
#   joint_state_broadcaster   joint_state_broadcaster/...  active
#   standby_controller_a      humanoid_control/StandbyController        inactive
#   standby_controller_b      humanoid_control/StandbyController        inactive
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

## What's the FSM doing differently?

| Operation | FSM (`mode_manager`) | Raw `ros2 control` |
|---|---|---|
| Gate `LOAD` on current state | Yes — rejects from non-DAMPING | No — happy to go ZERO_TORQUE → STANDBY directly |
| Gate `START_*` on `is_finished` | Yes | No |
| Auto-DAMP on `/safety_status` | Yes | No — you have to script it |
| Publish `/control_mode` | Yes | No — `list_controllers` is your only state view |
| React to `/joy` | Yes | No |

When you're done debugging, **re-enable `mode_manager`** before
operating in production. Its gates and the auto-DAMP path are real
safety properties; the convenience of bypassing them is for the
operator who's watching the robot, not for unattended use.

## See also

- [Five-mode FSM](../concepts/five_mode_fsm.md)
- [First real-hardware bringup](./first_real_bringup.md)
- [Reference → Controllers](../reference/controllers.md)
