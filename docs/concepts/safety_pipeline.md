---
title: Safety pipeline
---

# Safety pipeline

`Humanoid Control`'s safety layer is **layered** rather than concentrated.
Several mechanisms each enforce one piece of the contract: a controller
that produces a bad command is automatically swapped to a compliant
fallback by `ros2_control` itself, and transport-level faults are surfaced
as telemetry so the operator (or a supervising client) can react. There is
deliberately **no** single node that watches everything and forces a mode —
the model mirrors the minimal `ros2_control` reference.

![Safety pipeline: fault to DAMPING in ≤1 tick](/img/diagrams/concepts__safety_pipeline__01.svg)

## Layer 1 — Hardware plugins detect transport faults

`RobstrideSystem`, `SitoSystem`, and the EtherCAT plugin observe
**transport-level conditions** at every `read()` tick:

| Condition | Detection |
|---|---|
| `BUS_OFF` | The kernel CAN socket couldn't be opened, or returned `ENETDOWN`. Sticky — set in `on_configure`, only cleared on the next `on_activate`. |
| `RX_TIMEOUT` | One or more joints haven't reported an `OperationStatus` frame in > `rx_timeout_ms` (default 200 ms ≈ 10 ticks at 50 Hz). |
| `TX_QUEUE_OVERRUN` | The bus library's outbound SPSC ring overflowed (RT producer faster than the I/O thread can drain to the kernel). |
| `MOTOR_FAULT` | A Robstride status / fault-report frame indicated a non-OK motor state. |
| `TEMPERATURE_LIMIT` | A specific overtemperature bit was set in a motor's fault frame. |
| `INVALID_FRAME` | A frame on the bus had the wrong comm-type code or DLC for the protocol. |

The plugin publishes `humanoid_control_msgs/SafetyStatus` on `/safety_status` —
TRANSIENT_LOCAL durability so late-joining subscribers (rqt, an operator
dashboard) immediately see the most recent value. The `source` field
carries the bus interface name
(`humanoid_devices_robstride/can0`, etc.), so an operator can tell which bus
flagged.

Each tick, the plugin rebuilds `flags` from **currently observed**
conditions, not accumulated history. The exception is `BUS_OFF` —
which can't self-recover without a configure round-trip — which
sticks until activate. That choice avoids two bad failure modes:

- **No-sticky-anywhere**: a single EMI glitch would condemn the robot
  to FAULT for the rest of the activation.
- **Sticky-everywhere**: even transient drops would require an
  operator reset to clear, masking when the bus is actually healthy
  now.

Per-bit publish only happens **on change**, so the topic stays
quiet (level=0, flags=0) for a healthy robot and emits exactly one
message per state transition.

## Layer 2 — Controllers validate their own commands

The hardware plugins are not the only ones who can refuse to do
something. Each controller's `update()` returns a
`controller_interface::return_type` that the controller_manager
inspects:

| Controller | Reason it might return `ERROR` |
|---|---|
| `RLPolicyController` | NaN / non-finite observation, wrong tensor size, action outside configured limits |
| `RemotePolicyController` | `MITCommand` joint_names don't match claimed order, array length mismatch, stale command (configurable policy) |
| `StandbyController` | `pose_segment_N` malformed (caught at `on_configure`, not `update`) |

A non-OK `return_type` triggers the controller_manager's
**`fallback_controllers`** mechanism — see Layer 3.

`RemotePolicyController` — the System 1/2 external-command ingress —
additionally has a **stale-command policy**: if the external source's
`MITCommand` hasn't arrived within `stale_command_timeout_ms`
(default 100 ms = 5 ticks at 50 Hz, measured against arrival time at the
subscription callback — not against `MITCommand.header.stamp` — so
publisher clock skew is irrelevant), the controller writes a fallback
pattern rather than re-using the last command. Default `passive` → a
**damped hold**: zero stiffness, high damping (`kD = damping_scalar`,
default 6.0, matching DAMPING mode), holding the live joint position — the
arms stay damped, not limp. (The same damped hold also applies when REMOTE
is first entered, before any `MITCommand` has arrived.) Alternative `hold`
→ freeze at the last commanded pose. Either way the controller stays alive
and active; the choice is whether to "fail compliant" or "fail rigid".

`RLPolicyController` has no such command stream — it runs inference
in-process (System 0), so there is nothing to go stale. It guards
against bad *output* instead: a NaN / non-finite action returns
`ERROR` and falls through to Layer 3.

## Layer 3 — controller_manager's `fallback_controllers`

Every active-policy controller is configured with
`fallback_controllers: [damping_controller]` in
`humanoid_control_lite_controllers.yaml`. The controller_manager interprets this
as "if this controller returns ERROR, automatically deactivate it
and activate the fallback".

The hierarchy is **conservative to most-conservative**:

```
RLPolicyController     → damping_controller
RemotePolicyController → damping_controller
StandbyController      → damping_controller
DampingController      → zero_torque_controller
ZeroTorqueController   → (no fallback — final fall-back)
```

`zero_torque_controller` is the unique safer-than-damping option,
reserved for cases where DAMPING itself can't be applied (state
interface unavailable, hardware plugin dead). It writes 0 to every
interface — no risk of unintended motion regardless of state.

## Layer 4 — `/safety_status` is operator telemetry

There is deliberately **no** automatic `/safety_status` → DAMP path. The
old `mode_manager` node subscribed to `/safety_status` and forced a STRICT
switch to DAMPING on any non-OK level; that node is deleted, and nothing
replaced its auto-DAMP behavior.

Instead, `/safety_status` is **telemetry**. Bus and motor faults
(`RX_TIMEOUT`, `MOTOR_FAULT`, `TEMPERATURE_LIMIT`, `BUS_OFF`, and the rest)
are published for a human operator — or a supervising client — to see and
react to: press `X` to DAMP or `BACK` to STOP. What *is* automatic is
Layer 3: a controller that turns a fault into a bad command (a non-finite
observation, say) returns `ERROR`, and the controller_manager activates its
`fallback_controllers` with no operator in the loop.

This is a deliberate reduction to the reference's minimal model. The two
automatic guarantees that remain — a controller catching its own bad
command (Layer 2) and the controller_manager swapping in the fallback
(Layer 3) — cover the case that actually needs sub-tick reaction. Reacting
to a *reported* bus fault is left to the operator, who can always DAMP or
STOP from the gamepad.

## Layer 5 — RT update() discipline

A subtler "safety" layer that's worth naming: the RT `update()` paths
follow the standard RT-safety rules.

- **No allocations on the tick.** Every controller / hardware plugin
  pre-allocates buffers in `on_init` / `on_configure`. The
  `realtime_tools::RealtimeBuffer` and `realtime_tools::RealtimePublisher`
  primitives are the path for any RT-to-non-RT data movement.
- **No DDS-blocking calls.** Publishers go through `RealtimePublisher`'s
  `trylock` pattern — drop the message if the non-RT thread is mid-publish,
  rather than blocking the tick.
- **No exceptions across the RT boundary.** A throw inside `update()`
  would unwind into the controller_manager's RT thread, which is
  generally not safe under PREEMPT_RT.
- **No logging at tick rate.** Use `RCLCPP_*_THROTTLE` or buffer the
  message into a non-RT publisher.

Violating these doesn't (directly) cause a safety incident, but it
causes scheduler jitter that can make the higher layers slow to
react — RX_TIMEOUT trips spuriously because the read thread missed
its slot, etc.

## Summary

| Layer | Owner | Triggers |
|---|---|---|
| 1. Transport-level | hardware plugin | Bus / motor faults → `SafetyStatus.flags` |
| 2. Command-validity | controller | NaN / size mismatch / stale → `return_type::ERROR` |
| 3. Controller-manager fallback | controller_manager | `ERROR` → activate the controller's `fallback_controllers` |
| 4. Fault telemetry | `/safety_status` subscribers | Bus / motor faults reported for the operator (or a client) to react — no automatic DAMP |
| 5. RT discipline | every controller / plugin | (preventative — keeps the other layers responsive) |

## See also

- [How-to → Recover from a fault](../how_to/recover_from_fault.md) — operator-side runbook.
- [Reference → Messages → SafetyStatus](../reference/messages.md) — full bit table.
- [Five-mode FSM](./five_mode_fsm.md) — the modes and flat `joy_teleop` switching.
