---
title: MuJoCo + full FSM walkthrough
sidebar_position: 2
---

# Tutorial: MuJoCo + the full FSM, with a gamepad

A guided lesson on the five control modes. You'll bring up Lite in
MuJoCo, plug in a gamepad, and drive every mode from the buttons.

Switching is **flat and direct**: the stock `joy_teleop` node maps each
gamepad button straight to a `controller_manager/switch_controller`
call — activate one mode controller, deactivate its siblings. There is
**no state machine, no ordering, no gating**. Any mode reachable from
any state: you can jump straight from ZERO_TORQUE into LOCOMOTION, or
from a running policy back to STANDBY, in a single button press.
(The "FSM" in this page's title is historical; the five modes are the
same, only the arbitration is now this flat mapping.)

Because this is sim, no hardware can be damaged — push every button and
see what happens. By the end you'll know what each mode looks like
under physics.

This is **the** tutorial to do before any operator-driven session
on real hardware.

## Time + materials

- 20–30 minutes
- A USB gamepad (Xbox-layout is the default; anything `joy_node`
  recognises works)
- A working workspace build
- No robot needed

## Step 0 — Confirm the gamepad is detected

Plug in the gamepad. In a terminal:

```bash
ls /dev/input/js0
# /dev/input/js0       ← good
```

Quick test that `joy_node` will be happy (inside `pixi shell`):

```bash
cd humanoid_control_ws && pixi shell
ros2 run joy joy_node &
ros2 topic echo --once /joy
# Should print a Joy message with buttons[] and axes[] arrays.
killall joy_node
```

If `joy_node` errors with permissions, your user isn't in the
`input` group — `sudo usermod -aG input $USER` and log out / in.

## Step 1 — Launch with the gamepad

```bash
ros2 launch humanoid_bringup_lite mujoco.launch.py
# `enable_gamepad:=true` is already the default; the launch hard-fails
# if no joystick is detected. Pass enable_gamepad:=false to bypass.
# `enable_joy_teleop:=true` is also default — it starts the joy_teleop
# node that maps buttons → switch_controller. Pass
# enable_joy_teleop:=false to bring the stack up with no button bindings.
```

Two windows / processes come up:
- The MuJoCo viewer with Lite at zero pose.
- `joy_node` reading `/dev/input/js0`, and `joy_teleop` translating its
  buttons into controller switches.

For an extra live URDF view, open a second terminal and run
`ros2 run humanoid_bringup_lite rerun_viz` or
`ros2 run humanoid_bringup_lite viser_viz`.

In a second terminal:

```bash
cd humanoid_control_ws
pixi shell
ros2 control list_controllers
# zero_torque_controller       active
# (the other mode controllers loaded inactive)
```

There is no `/control_mode` topic — the active mode *is* whichever
controller `ros2 control list_controllers` reports as `active`. Keep
that command handy and re-run it after every button press to watch the
mode change.

## Step 2 — Mode: ZERO_TORQUE (start state)

You're already here. The motors are alive but the controller writes
0 to every command interface. Under MuJoCo physics with gravity, the
arms hang at their zero-pose; if you drag a joint in the viewer
mouse interaction you can move it freely (no resistance).

This is the "alive but inert" state — the operator's safe default, and
what **BACK** (STOP) returns you to.

## Step 3 — Press X: DAMP

Press **X** on the gamepad. `joy_teleop` activates `damping_controller`
and deactivates whatever was running:

```bash
ros2 control list_controllers
# damping_controller           active
# zero_torque_controller       inactive
```

Watch the MuJoCo arms: they now *resist* dragging. Stiffness is 0
so they don't actively pull back, but damping (default 1.0 N·m·s/rad)
viscously opposes velocity. The arms sag under gravity but slowly.

This is the **compliant fail-safe**. Any time you're worried, press
X — it works from any state, even mid-policy, because the switch has no
preconditions.

:::note[Headless equivalent]
Every button is just a `switch_controllers` call under the hood. With no
gamepad (or `enable_joy_teleop:=false`) you fire the exact same
transition yourself:

```bash
ros2 control switch_controllers \
    --activate damping_controller \
    --deactivate zero_torque_controller
```

`joy_teleop` reads `joy_teleop_lite.yaml`, which maps each button to one
of these calls.
:::

## Step 4 — Press L1 + A: STANDBY

Press **L1 + A** (hold L1, press A) — this activates Pose A
(`standby_controller_a`). `L1 + B` and `L1 + Y` activate two other
poses (`standby_controller_b`, `standby_controller_y`). The three poses
are independent, and because switching is flat you can hop **directly**
between them — L1+A then L1+B swaps A → B with no DAMPING step in
between.

`StandbyController` has **no gain ramp**: it applies its constant target
PD from the very first tick. It seeds its setpoint to the **current
measured joint positions**, then interpolates that setpoint to the
target pose over a couple of seconds. Because the setpoint starts at
where the arms actually are, there is **no jump** — this makes STANDBY
safe to enter from any state, including from a running policy.

```bash
ros2 control list_controllers
# standby_controller_a         active
```

Watch the MuJoCo arms glide from wherever they were into the piano-ready
pose (shoulders rolled out, elbows bent in). They should be visibly
stiffer than DAMPING — try dragging in MuJoCo, they'll pull back to the
standby pose. You don't have to wait for any "finished" signal before
the next switch: there is no gate. Press L1+A again from STANDBY and it
just re-seeds and re-runs the interpolation.

## Step 5 — Press R1 + B: REMOTE

Press **R1 + B**. `remote_policy_controller` goes active immediately —
no need to be in STANDBY first, no `is_finished` gate:

```bash
ros2 control list_controllers
# remote_policy_controller     active
```

`remote_policy_controller` is now claiming the command interfaces
and looking for `MITCommand` on `/remote_policy_controller/command`.
Nothing is publishing yet. On entering REMOTE before any `MITCommand`
arrives — and again after >100 ms (the `stale_command_timeout_ms`)
without one — its `passive` stale-command policy holds a **damped** pose:
zero stiffness, high damping (like DAMPING mode), holding the live joint
position. The arms in MuJoCo sag and settle under damping but stay
damped — they are not free-swinging.

This is **the expected behavior** without an external command source.
`RemotePolicyController` is the System 1/2 external-command ingress: to
drive it properly you'd run a non-real-time source publishing
`MITCommand` over DDS (e.g. the gravity-compensation runner). The
learned tracking policy does *not* use this path — it runs in-process
under LOCOMOTION, which is the next tutorial.

For now, fake an MITCommand directly to verify the controller is
listening:

```bash
ros2 topic pub --once /remote_policy_controller/command \
    humanoid_control_msgs/msg/MITCommand \
    "{header: {stamp: now},
      joint_names: ['left_shoulder_pitch', 'left_shoulder_roll', 'left_shoulder_yaw',
                    'left_elbow_pitch', 'left_wrist_yaw', 'left_wrist_roll', 'left_wrist_pitch',
                    'right_shoulder_pitch', 'right_shoulder_roll', 'right_shoulder_yaw',
                    'right_elbow_pitch', 'right_wrist_yaw', 'right_wrist_roll', 'right_wrist_pitch'],
      position: [0.3, -1.0, 0.0, -1.7, -1.2, 0.0, 0.3,
                 0.3,  1.0, 0.0, -1.7,  1.2, 0.0, -0.3],
      velocity: [0,0,0,0,0,0,0, 0,0,0,0,0,0,0],
      effort:   [0,0,0,0,0,0,0, 0,0,0,0,0,0,0],
      stiffness:[50,50,50,50,50,50,50, 50,50,50,50,50,50,50],
      damping:  [2,2,2,2,2,2,2, 2,2,2,2,2,2,2]}"
```

The arms snap toward that pose — one publish only, so within 100 ms
they relax back into the damped hold (zero stiffness, high damping) as
the stale-command policy kicks in. Repeat the publish to drive
continuously, or move to the policy tutorial for the auto-publish path.

## Step 6 — Press X: back to DAMP

Press **X** again. The motors are now compliant. Because switching is
flat, this works out of REMOTE (or any mode) with no ordering
requirement — X always lands you in DAMPING.

## Step 7 — Press BACK: STOP

Press **BACK**. `joy_teleop` activates `zero_torque_controller`:

```bash
ros2 control list_controllers
# zero_torque_controller       active
```

STOP is **not** a shutdown. `zero_torque_controller` stays enabled and
holds zero torque on every joint — you're back at the Step 2 start
state, and you can press any other button to leave it again. There is no
button that tears the stack down.

To actually exit, `Ctrl+C` the launch terminal. The hardware plugin's
`on_deactivate` runs, sending CAN **Disable** to every joint (a no-op in
MuJoCo but the real safety stop on silicon), and `mujoco_sim` shuts down
cleanly.

## Step 8 — Go straight to LOCOMOTION

To prove the flat switching, don't walk up through the modes at all.
From ZERO_TORQUE (or literally any mode), press **R1 + A**:

```bash
ros2 control list_controllers
# rl_policy_controller         active
```

`rl_policy_controller` (LOCOMOTION) is entered **directly, at full
authority** — no soft-start, no required STANDBY, no `is_finished`
precondition. With no ONNX policy prepared (or a build without
`onnxruntime`), `RLPolicyController` falls back to `PlaceholderPolicy`
(zero actions), so the motors just stay where they are; the point here
is that the switch itself is unconditional.

If a mode controller ever errors (e.g. the policy emits a non-finite
action), it doesn't need the operator or a safety topic to catch it: the
controller_manager's native `fallback_controllers` fires automatically —
each mode controller falls back to `damping_controller`, and
`damping_controller` falls back to `zero_torque_controller`. The
`/safety_status` topic is telemetry you can watch, not a trigger that
switches modes for you.

## What you came away with

| Skill | Page where it's documented in full |
|---|---|
| The five control modes and what each writes | [Concepts → Five control modes](../concepts/five_mode_fsm.md) |
| Flat `joy_teleop` button → `switch_controller` mapping (no ordering) | [Quick reference](../reference/quick_reference.md) |
| Native fault fallback (mode → damping → zero_torque) | [Concepts → Safety pipeline](../concepts/safety_pipeline.md) |
| Gamepad button → controller mapping | [Quick reference](../reference/quick_reference.md) |
| The MIT publish path | [`MITCommand` schema](../reference/messages.md) |

## Next

- [Tutorials → Run a tracking policy](./tracking_policy.md) — drive
  LOCOMOTION with a real in-process ONNX policy.
- [How-to → First real-hardware bringup](../how_to/first_real_bringup.md)
  — same modes, same buttons, but on silicon.
