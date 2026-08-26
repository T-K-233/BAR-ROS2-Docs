# Five-mode FSM

The operator-facing control surface is **five control modes, each one a
`controller_interface::ControllerInterface` plugin**, with **only one mode
controller active at any time** — the controller_manager's
interface-claiming machinery enforces that mutual exclusion mechanically.
`joint_state_broadcaster` is the always-on telemetry stream alongside
whichever mode is active.

The modes have not changed. What changed is the **arbitration**. There is
no longer a finite state machine with ordering rules, and no dedicated
`mode_manager` node. Switching is now **flat**: the stock `joy_teleop`
node (from ROS `teleop_tools`) maps each gamepad button **directly** to a
`/controller_manager/switch_controller` call, and **any mode is reachable
from any other mode** with no gating. (This page keeps its historical
"FSM" name because the sidebar and several other pages link to it.)

![Five-mode FSM with joy bindings](/img/diagrams/concepts__five_mode_fsm__01.svg)

## Why flat switching

The previous design routed the gamepad through a hand-written FSM
(`mode_manager`) that enforced ordering rules — DAMP from anywhere, LOAD
only from DAMPING, START only from a finished STANDBY, QUIT only from a
resting state. That ceremony has been removed in favour of the
ros2-control-idiomatic pattern (reference: `qiayuanl/unitree_bringup`,
`config/g1/joy.yaml`): the gamepad drives `switch_controller` directly, and
every mode is designed to be **safe to enter from any state**, so no
gating is needed.

Two properties make the flat model safe without an FSM:

1. **Every button is absolute, not relative.** Each button activates
   exactly one controller and deactivates its siblings, so "press DAMP"
   lands you in DAMPING regardless of where you were — the same
   single-axis safety the FSM's universal DAMP edge used to give, now a
   property of the button map itself.
2. **Every mode is jump-free on entry.** STANDBY seeds its position
   setpoint to the **current measured** joint positions and interpolates
   from there to the target pose, so it can be entered from a running
   policy with no discontinuity; DAMPING captures the live position;
   ZERO_TORQUE writes zero. Because no entry is unsafe, the old "only
   allowed when `is_finished`" gates are unnecessary. You can go
   ZERO_TORQUE → LOCOMOTION or LOCOMOTION → STANDBY directly.

The trade is deliberate: less mechanism (no FSM node, no ordering rules,
no `/control_mode` telemetry topic, no per-mode Trigger services), closer
to stock ros2-control, at the cost of the operator being able to command
any transition — including ones the FSM used to reject.

## The five modes

| Mode | Plugin | What it writes per tick | Use it for |
|---|---|---|---|
| **ZERO_TORQUE** | `humanoid_control::DampingController` at `damping: 0.0` | `0` to all 5 MIT interfaces on every joint | Startup default and the STOP target (`BACK`). Also the final fault fallback (DAMPING falls back here). Robot is alive but inert — motors enabled, zero torque. |
| **DAMPING** | `humanoid_control::DampingController` | `stiffness=0`, `damping=damping_value`, `position=captured`, `velocity=0`, `effort=0` | Compliant fail-safe. Robot stays soft under gravity but resists velocity. The native fallback target for any mode controller that errors. |
| **STANDBY** | `humanoid_control::StandbyController` | Interpolated `position` from the **current measured** joint positions toward a YAML target pose; constant target `K_p`/`K_d` from t=0 (**no ramp**) | Animate the arms to a ready pose. Because the setpoint starts at the measured position, it is safe to enter from any state — including a running policy — with no jump. Spawned as **three instances** — `standby_controller_a` / `_b` / `_y` (Poses A / B / Y) — the same plugin with different YAML poses. Still publishes `~/state` (`StandbyState`), but nothing gates on `is_finished` anymore. |
| **LOCOMOTION** | `humanoid_control::RLPolicyController` | In-process ONNX inference (low-latency, C++): packs obs, advances the motion reference if the task has one, writes commands | **Every learned policy** — tracking, piano, locomotion. They differ by the loaded `.onnx` and its motion source (see below); the ONNX `task_type` selects the term set. This is the System 0 real-time path. Entered directly at full authority (no soft-start). |
| **REMOTE** | `humanoid_control::RemotePolicyController` | `MITCommand` consumed from `~/command` over DDS | System 1/2 external-command ingress: a *non*-real-time source publishes commands (gravity-comp today via `Lite-Gravity-Compensation`; VLA / manipulation later). Not used by the learned policies. |

Full per-controller parameter tables live in
[Reference → Controllers](../reference/controllers.md).

### Where a policy's motion reference comes from

A locomotion policy has no motion reference at all — it is driven live by the
`/cmd_vel` twist. Tasks that *do* follow a reference get it from one of two
places, resolved when the controller configures:

- **Embedded in the ONNX graph.** mjlab's motion-tracking exporter bundles the
  whole reference motion into the checkpoint as initializers and adds a
  `time_step` input, so the graph itself is the motion source. Such a checkpoint
  is self-contained: no `.mcap` bag, no dataset fetch, and the frame indexing is
  exactly the one the policy trained with. `humanoid_control_policy prepare`
  detects this shape and skips the conversion step entirely.
- **A `.mcap` motion bag.** The older path, still used by the piano task (a
  key-pressed song bag plus a live key-state term) and by any tracking export
  that does not carry its motion. `prepare` builds the bag from a LeRobot
  dataset and points the controller at it via `motion_file`.

If a checkpoint carries its own motion, that wins and any `motion_file` you pass
is ignored (with a warning). A non-empty `motion_file` that fails to load is a
hard error rather than a silent fallback — the policy's observation would be
wrong without it.

## Button map

The mapping lives in `lite_joy_teleop.yaml` (with siblings
`biped_joy_teleop.yaml` and `prime_joy_teleop.yaml`) and is read by the
stock `joy_teleop` node. Each entry maps a button — or an `L1`/`R1` chord —
to **one** `switch_controller` call that **activates one controller and
deactivates its siblings**, with **BEST_EFFORT** strictness. There is no
ordering: any row fires from any current mode.

| Button | Mode | Activates |
|---|---|---|
| `X` | DAMP | `damping_controller` |
| `L1` + `A` | STANDBY (Pose A) | `standby_controller_a` |
| `L1` + `B` | STANDBY (Pose B) | `standby_controller_b` |
| `L1` + `Y` | STANDBY (Pose Y) | `standby_controller_y` |
| `R1` + `A` | LOCOMOTION | `rl_policy_controller` |
| `R1` + `B` | REMOTE | `remote_policy_controller` |
| `BACK` | STOP | *nothing* — deactivates every mode |

`teleop_tools` is not in robostack-jazzy. The `berkeley-humanoids` channel
publishes `ros-jazzy-joy-teleop` and `ros-jazzy-teleop-tools-msgs`, so a
channel install gets it as a package; a source workspace builds it from
`humanoid_control.repos`.

`BACK` activates nothing: it deactivates every mode and the hardware holds
each joint's safe state. The motors hold zero torque but
stay **enabled** — the robot is still on the bus. It is **not** a
power-down. Full CAN Disable happens only on `Ctrl+C`, when the hardware
plugin's `on_deactivate` runs. There is no button-driven shutdown and no
sequenced QUIT anymore.

### Driving it without a gamepad

There are no `/humanoid_control/mode/*` Trigger services anymore.
Programmatic clients call `/controller_manager/switch_controller`
directly; a headless operator uses the stock CLI:

```
ros2 control switch_controllers --activate standby_controller_a --deactivate damping_controller
```

### Which mode is active?

The `/control_mode` topic is **gone** — nothing publishes it. (The
`humanoid_control_msgs/ControlMode` message type still exists, because the
`humanoid_control_msgs_dds` wire bridge generates and tests it, but no node
publishes or subscribes the topic.) Anything that needs to know which mode
is active now polls `/controller_manager/list_controllers` and looks for
the active mode controller — the MuJoCo `HomePosePlugin` support band and
the Prime `erob_impedance_manager` both do this.

## Fault handling is native fallback

Fault response is now **purely** ros2-control's own `fallback_controllers`
mechanism. Each mode controller declares
`fallback_controllers: [damping_controller]` (and `damping_controller`
declares no fallback of its own, because the hardware's safe state is the
floor); if a controller's
`update()` returns `ERROR` — e.g. a non-finite observation — the
controller_manager deactivates it and activates its fallback.

There is **no** automatic `/safety_status` → DAMP path anymore. Bus faults
(RX timeout, motor fault, overtemp) are still published on `/safety_status`
as **telemetry**, but nothing auto-DAMPs on them — the operator reacts
(`X` to DAMP, `BACK` to STOP) or a controller error trips the native
fallback. See [Concepts → Safety pipeline](./safety_pipeline.md) for the
full picture.

## Pose and policy are independent

The three `L1` combos select **which standby pose** to animate to; the two
`R1` combos select **which policy** to run. The two axes are orthogonal,
and nothing is gated:

- `L1+A` / `L1+B` / `L1+Y` load `standby_controller_a` / `_b` / `_y`
  (Poses A / B / Y). All three are the same `StandbyController` plugin
  (source `standby_controller.cpp`, unchanged) configured with **different
  YAML poses**.
- From any standby pose — or from any other mode — you can start **either**
  policy: `R1+A` → LOCOMOTION (`rl_policy_controller`), `R1+B` → REMOTE
  (`remote_policy_controller`). There is no pairing and no gate — `L1+A`
  then `R1+B` is exactly as valid as `L1+A` then `R1+A`.

Because switching is flat, you can now go **directly** from one standby
pose to another: `L1+B` from Pose A activates `standby_controller_b` and
deactivates `standby_controller_a` in one call, and because STANDBY seeds
to the current measured position the arms move smoothly to the new pose
with no DAMP in between. (Under the old FSM, LOAD was admissible only from
DAMPING, so a pose change required a DAMP first; that gate is gone.)

The **policy target is still chosen at runtime**, not by a launch arg — it
is simply which `R1` button you press.

## What joy_teleop is *not*

- **Not a safety system on its own.** It only translates buttons into
  `switch_controller` calls. Detecting transport failures is the hardware
  plugins' job (they publish `/safety_status`); catching a bad command is
  the controller's job (it returns `ERROR` and the controller_manager
  activates its fallback); enforcing "no two controllers claim the same
  command interface" is the controller_manager's job.
- **Not a custom node.** `joy_teleop` is the stock `teleop_tools` node
  driven entirely by YAML — there is no bespoke FSM executable to maintain.
  The old `mode_manager` node is deleted.
- **Not running during calibration.** `calibrate.launch.py` passes
  `enable_joy_teleop:=false` (the launch arg was renamed from
  `enable_mode_manager`) so button presses don't interfere with the raw
  `/lite/joint_states` sampling. Drive controllers by hand with
  `ros2 control switch_controllers` if you need a mode change during
  calibration.

## See also

- [Reference → Controllers](../reference/controllers.md) — per-plugin parameter tables.
- [Concepts → Safety pipeline](./safety_pipeline.md) — the native fallback model and `/safety_status` as telemetry.
- [How-to → Switch controllers by hand](../how_to/switch_controllers_manually.md).
