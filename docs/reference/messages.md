# Messages

Custom ROS 2 interfaces. **Frozen** once a trained policy depends on the
schema (changing the layout forces retraining). `humanoid_control_msgs` ships four
messages. The live piano key state is **not** a custom message — it
travels as a stock `std_msgs/Float32MultiArray` on `/piano/key_state`,
which keeps `humanoid_controllers` free of any `pianist_msgs` dependency.

:::note[Off-ROS consumers]
Tier-3 (non-`rclpy`) clients get these types from
[`humanoid_control_msgs_dds`](packages.md#humanoid_control_msgs_dds) — generated from the same `.msg`
and wire-compatible — usually via the `lite_sdk2` SDK. See
[Talk to Humanoid Control from Python](../how_to/talk_to_humanoid_control_from_python.md).
:::

## Topology

![humanoid_control_msgs pub/sub topology](/img/diagrams/reference__messages__01.svg)

## `humanoid_control_msgs/MITCommand`

The five-MIT-mode-interface command record. It is written **internally**
by `RLPolicyController` each tick (in-process, never published), and it is
the **on-wire format** a System 1/2 external-command source (gravity-comp
runner today, VLA later) publishes over DDS into `RemotePolicyController`.
Mirrors the **five MIT-mode command interfaces** one-to-one.

```
std_msgs/Header header
string[] joint_names      # validated against the controller's claimed order
float64[] position
float64[] velocity
float64[] effort
float64[] stiffness
float64[] damping
```

All arrays must have the same length as `joint_names`. The controller rejects
the message if the order doesn't match its `joints:` parameter.

:::tip[Why all five fields, every message]
Sending only `position` (Cartesian-style) would force the receiver to assume
defaults for the rest. By making the policy send all five, the **intent is
explicit**: a "position-only" command would still send `velocity=0`,
`stiffness=Kp_target`, `damping=Kd_target`, `effort=0` — making the controller
re-creation fully reproducible.
:::

## `humanoid_control_msgs/ControlMode`

Mode telemetry message. **No longer published on any topic** — the
`mode_manager` node that published `/control_mode` at 50 Hz has been removed,
and nothing publishes or subscribes the topic today. The message **type is
retained** because [`humanoid_control_msgs_dds`](packages.md#humanoid_control_msgs_dds)
generates and tests a wire-compatible mirror of it. Read the active mode from
`/controller_manager/list_controllers` instead.

```
std_msgs/Header header

uint8 ZERO_TORQUE = 0
uint8 DAMPING     = 1
uint8 STANDBY     = 2
uint8 LOCOMOTION  = 3
uint8 REMOTE      = 4

uint8 mode
string controller_name      # spawned controller name (e.g. "damping_controller")
string status_message       # human-readable, may carry rejection reason
```

The numeric `mode` field uses the explicit constants above. Consumers should
match against the `uint8 <name> = <value>` defines, not hard-code integers.

## `humanoid_control_msgs/StandbyState`

Published by each `StandbyController` instance on `~/state` — which resolves
to `/standby_controller_a/state` (Pose A) or `/standby_controller_b/state`
(Pose B), one topic per pose — with `TRANSIENT_LOCAL` (latched) QoS so a
late-joining subscriber immediately sees the most recent value.

```
std_msgs/Header header
uint32 current_segment    # index into the pose sequence
uint32 total_segments
float64 progress          # [0, 1] within the current segment
bool is_finished          # true once final pose + final gains reached
```

This is **telemetry only**: `is_finished` reports when the final pose and gains
are reached, but **nothing gates on it** anymore — any mode can be entered from
STANDBY (or any other state) at any time.

## `humanoid_control_msgs/SafetyStatus`

Layered safety telemetry. Any hardware plugin or controller may publish; the
`flags` bitmask is **plugin-specific**.

```
std_msgs/Header header

uint8 OK       = 0
uint8 WARNING  = 1   # degraded but commands still honored
uint8 FAULT    = 2   # commands no longer guaranteed; transition recommended
uint8 CRITICAL = 3   # immediate fault fallback required

uint8 level
string source       # e.g. "humanoid_devices_robstride/can0", "rl_policy_controller"
uint32 flags        # plugin-specific bitmask
string message
```

Bit layout (see [Concepts → Safety pipeline](../concepts/safety_pipeline.md)
for the per-flag detection logic):

| Bit | Constant | Meaning |
|---|---|---|
| 0 | `FLAG_BUS_OFF` | Kernel CAN socket couldn't open or returned `ENETDOWN`. Sticky until `on_activate`. |
| 1 | `FLAG_RX_TIMEOUT` | One or more joints stopped reporting status frames within `rx_timeout_ms`. |
| 2 | `FLAG_TX_QUEUE_OVERRUN` | Outbound SPSC ring overflowed. |
| 3 | `FLAG_MOTOR_FAULT` | A Robstride status frame reported a non-OK motor state. |
| 4 | `FLAG_TEMPERATURE_LIMIT` | A motor exceeded its overtemperature threshold. |
| 5 | `FLAG_INVALID_FRAME` | A frame on the bus had the wrong comm-type code or DLC. |

## Live piano key state (`std_msgs/Float32MultiArray`)

There is no custom message for the live key state. It is published as a
stock `std_msgs/Float32MultiArray` on `/piano/key_state` (RELIABLE +
KEEP_LAST(1)) — one `0.0`/`1.0` entry per key — by
`pianist_policy/piano_state_bridge` in sim and
`pianist_policy/midi_keyboard_driver` on real hardware. The in-process
`RLPolicyController` consumes it as the `key_pressed` extern observation
term.

Using a generic array (rather than a `pianist_msgs` type) is deliberate:
the core controller package never learns the piano task exists; it just
packs a named extern vector. The song's **goal** frame is not a topic —
it is baked into the `.mcap` motion bag the controller loads at
`on_configure` (and served as the `target_keys` reference term), so no
per-tick goal re-publish is needed.

The sim-side publisher (`piano_state_bridge`) binarises against
`KEY_TRIGGER_THRESHOLD = 0.70` (matching upstream
`T-K-233/Robot-Descriptions/robot_descriptions/piano/consts.py`).