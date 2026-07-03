---
title: MuJoCo + full FSM walkthrough
sidebar_position: 2
---

# Tutorial: MuJoCo + the full FSM, with a gamepad

A guided lesson on the five-mode FSM. You'll bring up Lite in MuJoCo,
plug in a gamepad, and walk every transition the FSM supports.
Because this is sim, no hardware can be damaged — push every button
and see what happens. By the end you'll know what each mode looks
like under physics and how the FSM gates work.

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
```

Two windows / processes come up:
- The MuJoCo viewer with Lite at zero pose.
- `joy_node` reading `/dev/input/js0`.

For an extra live URDF view, open a second terminal and run
`ros2 run humanoid_bringup_lite rerun_viz` or
`ros2 run humanoid_bringup_lite viser_viz`.

In a second terminal:

```bash
cd humanoid_control_ws
pixi shell
ros2 control list_controllers
# zero_torque_controller       active
# (the four other FSM controllers loaded inactive)

ros2 topic echo /control_mode
# mode: 0  (ZERO_TORQUE)
# controller_name: zero_torque_controller
```

Leave the `/control_mode` echo open — you'll watch it for every
transition.

## Step 2 — Mode 1: ZERO_TORQUE (start state)

You're already here. The motors are alive but the controller writes
0 to every command interface. Under MuJoCo physics with gravity, the
arms hang at their zero-pose; if you drag a joint in the viewer
mouse interaction you can move it freely (no resistance).

This is the "alive but inert" state — the operator's safe default.

## Step 3 — Transition: DAMP (any state → DAMPING)

Press **X** on the gamepad.

`/control_mode` should show:
```
mode: 1  (DAMPING)
controller_name: damping_controller
```

Watch the MuJoCo arms: they now *resist* dragging. Stiffness is 0
so they don't actively pull back, but damping (default 1.0 N·m·s/rad)
viscously opposes velocity. The arms sag under gravity but slowly.

This is the **compliant fail-safe**. Any time you're worried, press
X. The FSM accepts DAMP from any state — even mid-policy.

## Step 4 — Transition: LOAD (DAMPING → STANDBY)

Press **L1 + A** (hold L1, press A) — this loads **Pose A**
(`standby_controller_a`). `L1 + B` loads a *different* pose, **Pose B**
(`standby_controller_b`); the two poses are independent, and you can only
switch from one to the other by going through DAMPING first (there is no
direct A ↔ B switch).

The arms now ramp through a two-segment trajectory:
1. Segment 0 (~2 s): K_p/K_d ramp 0 → target while position
   interpolates to zero pose. You'll see the arms gently swing to
   "arms straight down".
2. Segment 1 (~2 s): position interpolates to the piano-ready pose
   (shoulders rolled out, elbows bent in). K_p/K_d stay at target.

While Standby is running (watch the topic for the pose you loaded — here
Pose A):
```bash
ros2 topic echo /standby_controller_a/state
# current_segment: 0, progress: 0.45, is_finished: false
# ...
# current_segment: 1, progress: 0.95, is_finished: false
# is_finished: true   ← the gate for the next transition opens here
```

The pose-ready arms should be visibly stiffer than DAMPING — try
dragging in MuJoCo, they'll pull back to the standby pose.

Now try pressing L1 + A again from STANDBY. The FSM rejects the
intent and writes the reason to `/control_mode.status_message`:
```
status_message: "LOAD_A ignored; must be in DAMPING"
```

That's the gating — LOAD is only legal from DAMPING.

## Step 5 — Transition: START_REMOTE (STANDBY → REMOTE)

**Wait for `is_finished:true`** in `/standby_controller_a/state` first
(the topic for the pose you loaded). Then press **R1 + B**.

`/control_mode` shows:
```
mode: 4  (REMOTE)
controller_name: remote_policy_controller
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

## Step 6 — Transition: DAMP (out of REMOTE)

Press **X** again. The motors are now compliant. From DAMPING you
can go anywhere — that's the safety guarantee.

## Step 7 — Transition: QUIT (DAMPING → exit)

Press **BACK**.

`mode_manager` shuts down (`rclcpp::shutdown()`). Watch the launch
terminal: most of the stack tears down. The launched processes
finish in their normal `on_deactivate` order, and the MuJoCo viewer
window closes.

**Try QUIT from STANDBY or REMOTE.** It's rejected:
```
status_message: "QUIT rejected; must be in ZERO_TORQUE or DAMPING"
```

The FSM forces a DAMP first. This is the safety property: you can't
exit while a policy is driving the arms.

## Step 8 — Try the locomotion combos

Relaunch and walk LOAD → START_LOCOMOTION (`L1+A` then `R1+A`).
With no ONNX policy prepared (or a build without
`onnxruntime`), `RLPolicyController` falls back to `PlaceholderPolicy`
(zero actions), so this transitions to LOCOMOTION but the motors just
stay where they are. Useful to verify the FSM gating works
symmetrically — try START_LOCOMOTION before STANDBY has
`is_finished:true` and it'll reject:
```
status_message: "START_LOCOMOTION rejected; standby not finished yet"
```

## What you came away with

| Skill | Page where it's documented in full |
|---|---|
| The five FSM modes and what each writes | [Concepts → Five-mode FSM](../concepts/five_mode_fsm.md) |
| Gating logic (LOAD only from DAMPING, START_* gated on is_finished) | same |
| The auto-DAMP safety path | [Concepts → Safety pipeline](../concepts/safety_pipeline.md) |
| Gamepad button → intent mapping | [Quick reference](../reference/quick_reference.md) |
| The MIT publish path | [`MITCommand` schema](../reference/messages.md) |

## Next

- [Tutorials → Run a tracking policy](./tracking_policy.md) — drive
  LOCOMOTION with a real in-process ONNX policy.
- [How-to → First real-hardware bringup](../how_to/first_real_bringup.md)
  — same FSM, but on silicon.
