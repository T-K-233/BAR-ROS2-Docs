# Controllers + FSM

Five `controller_interface::ControllerInterface` plugins. Mode switching is
**flat**: the stock `joy_teleop` node (ROS `teleop_tools`) maps gamepad
buttons **directly** to `/controller_manager/switch_controller` — there is no
arbitrating state machine or `mode_manager` node anymore. **Only one mode
controller is active at a time**; `joint_state_broadcaster` runs always.

## FSM summary

The five modes still exist as controllers, but there is **no finite-state
machine** arbitrating them: any mode can be entered from any other, in any
order (e.g. `ZERO_TORQUE → LOCOMOTION` directly). Switching is done by
`joy_teleop` (gamepad) or `ros2 control switch_controllers` (CLI); each button
activates one controller and deactivates its siblings with `BEST_EFFORT`
strictness. See [Concepts → Architecture](../concepts/architecture.md#five-mode-finite-state-machine)
for the mode overview.

## Plugin-by-plugin

### `humanoid_control/DampingController`

**Role**: joint-space damping hold, and the compliant fault fallback. One
instance, `damping_controller`, spawned per robot.

There is no longer a second instance for zero torque. Zero torque is not a
controller: it is what the hardware drives for any joint no controller claims,
so the robot is safe with nothing loaded at all. See [STOP](#stop) below. The *Springer Handbook of
Robotics* (Villani & De Schutter, "Force Control" §7.2.2) names the `K_P = 0`
case **damping control**, and zero torque is that law at `K_D = 0`. Unitree's
SDK draws the same line as two FSM ids rather than two implementations:
`ZeroTorque()` is id 0 and `Damp()` is id 1.

**Claims**: position, velocity, effort, stiffness, damping on every joint;
position and velocity state.

**Writes** every tick: the position captured at activation, zero velocity, zero
effort, zero stiffness, and `damping` on the velocity term. A MIT joint
therefore produces `tau = -damping * qdot`, which is zero torque at
`damping: 0.0`. A CiA402 joint has no impedance interface and cannot go limp, so
it tracks the captured position as a servo target instead.

**Parameters**:

| Param | Type | Default | Description |
|---|---|---|---|
| `joints` | `string[]` | — | Required. Joint names to claim (must match URDF). |
| `mit_joints` | `string[]` | `[]` | The subset exposing stiffness and damping. Empty means every joint. Configuring a name absent from `joints` is rejected. |
| `damping` | `float64` | — | Required, in `Nm/(rad/s)`. No default: this is a fault fallback, so an unstated gain would be an arbitrary one. `0.0` is a zero-torque limp. |

### `humanoid_control/StandbyController`

**Role**: linearly interpolate joint positions through a pose sequence toward a
ready pose. Gains are **constant at the target `K_p / K_d` from `t = 0`** —
there is **no gain ramp**. On activation the setpoint is **seeded to the
current measured joint positions** and interpolated from there, so entering
STANDBY is safe from **any** prior state (no snap).

**Instances**: spawned **once per configured pose** — `standby_controller_a`
(Pose A, `L1+A`) and `standby_controller_b` (Pose B, `L1+B`); the Lite arms
config adds a third, `standby_controller_y` (Pose Y, `L1+Y`). Same plugin class
(and same `standby_controller.cpp`), different pose parameters in the bringup
YAML. Each is activated directly by its gamepad button (via `joy_teleop`) or by
`ros2 control switch_controllers`.

**Parameters**:

| Param | Type | Description |
|---|---|---|
| `joints` | `string[]` | Required. |
| `target_stiffness` | `float64[]` | Per-joint target `K_p` (constant, held from activation). |
| `target_damping` | `float64[]` | Per-joint target `K_d` (constant, held from activation). |
| `segment_durations` | `float64[]` | Seconds per pose segment. Length determines how many pose segments are expected. |
| `pose_segment_<i>` | `float64[]` | Per-segment target pose vector; one parameter per segment index in `[0, len(segment_durations))`. Each is a per-joint position array sized to `len(joints)`. |

**Publishes**: `~/state` (`humanoid_control_msgs/StandbyState`) with `TRANSIENT_LOCAL` QoS —
i.e. `/standby_controller_a/state`, `/standby_controller_b/state` (and
`/standby_controller_y/state` on Lite), one per instance. This is **telemetry
only**: `is_finished` reports progress but **nothing gates on it** anymore (any
transition is allowed from any state). Watch the one matching the pose you
activated.

:::tip[How the bundled config interpolates]
`lite_controllers.yaml` configures each instance with **two
segments**, where the final `pose_segment` is that instance's target pose — the
standby instances differ only in this final pose (Pose A vs Pose B vs Pose Y).
Activating a standby button therefore animates the arms from their **current
measured position** to the chosen pose over the configured segments, holding the
target `K_p` / `K_d` constant the whole time (no gain ramp).
:::

`fallback_controllers: ["damping_controller"]` is set on the
controller-manager side so any non-`OK` `return_type` from `update()`
auto-deactivates Standby and activates Damping. This native
`fallback_controllers` mechanism — declared on every mode controller — is now
the **only** automatic fault response; there is no `/safety_status`-driven
auto-DAMP node anymore (`/safety_status` is telemetry the operator reacts to).

### `humanoid_control/RLPolicyController`

**Role**: **in-process** ONNX inference — this is the System 0 path that
runs *every* learned policy (tracking / piano / locomotion). Each RT
`update()` it packs the observation (`ObservationManager`), runs inference
(`OnnxPolicy`), reads the motion reference from the preloaded `.mcap`
(`ReferenceProvider`), maps the action across the full articulation
(`ActionMapper`), and writes the five MIT command interfaces — never
leaving the RT thread. Policies differ only by the loaded `.onnx` +
`.mcap`; the ONNX `task_type` metadata selects the term set. It is entered
**directly at full authority** — there is no soft-start ramp.

Its parameters come from the `rl_policy_controller` overlay that
`humanoid_control_policy prepare` (or `pianist_policy prepare`) transcodes from the
ONNX `custom_metadata_map` — they are not hand-written:

| Param | Type | Description |
|---|---|---|
| `joints` | `string[]` | Full articulation list. |
| `action_joint_names` | `string[]` | Subset the policy emits actions for; the rest are pinned to `position=0`. |
| `observation_names` | `string[]` | The flat observation vector, term by term (resolved by `ObservationManager`). |
| `body_names` | `string[]` | Reference-tracked bodies (for `motion_body_*` terms). |
| `default_joint_position` | `float64[]` | `q_default` in obs scaling and `pos = q_default + scale * a`. |
| `action_scale` | `float64[]` | Per-action-joint scale. |
| `stiffness`, `damping` | `float64[]` | Per-joint MIT gains written every tick. |
| `policy_checkpoint` | `string` | Path to the resolved `.onnx`. |
| `motion_file` | `string` | Path to the `.mcap` motion bag loaded at `on_configure`. |
| `observation_dim`, `action_dim` | `int` | ONNX I/O sizes. |

:::tip[ONNX runtime is opt-in]
`OnnxPolicy` (onnxruntime C++) is built only when onnxruntime is found at
build time — the conda `onnxruntime-cpp` package, pinned in `pixi.toml`.
Without it the controller falls
back to `PlaceholderPolicy` (zeros) — useful for smoke-testing controller
switching and the observation/reference plumbing without a real inference
dependency.
The contract (`PolicyMetadata` → overlay) is identical either way. See
[Policy runner](policy_runner.md).
:::

### `humanoid_control/RemotePolicyController`

**Role**: the **System 1/2 external-command ingress** (kept, unchanged).
A *non*-real-time source publishes `MITCommand` over DDS to `~/command`
(`RELIABLE` QoS depth 4); the controller validates joint order and hands
off via `realtime_tools::RealtimeBuffer` to the RT `update()`, with
arrival-time staleness gating. It is **not** used by the learned policies
anymore — those run in-process in `RLPolicyController`.

**Parameters**:

| Param | Type | Default | Description |
|---|---|---|---|
| `joints` | `string[]` | — | Required. |
| `stale_command_policy` | `string` | `passive` | `passive` or `hold`. `passive` is a **damped hold** — zero stiffness (`kP=0`) and high damping (`kD = damping`) while holding the live joint position, exactly like DAMPING mode; applied both on entering REMOTE before the first command **and** on stale dropouts (it no longer goes fully limp). `hold` is unchanged. |
| `stale_command_timeout_ms` | `int` | `100` | Staleness window measured against the message's **arrival time at the subscription callback**, not against `MITCommand.header.stamp`. Publisher clock skew is irrelevant. |
| `damping` | `float64` | — | Required, in `Nm/(rad/s)`. The gain of the `passive` damped hold. Match `damping_controller`'s value so the hold feels the same as the damping mode. |

The controller **rejects** any `MITCommand` whose `joint_names` doesn't match
its claimed order, or whose array lengths don't all match `joints.size()`.

Today the producer is the gravity-compensation runner
(`Lite-Gravity-Compensation` — raw CycloneDDS, no `rclpy`); next it will
be VLA / manipulation. These are deliberately out-of-process: slower,
deliberative, and tolerant of the DDS-hop latency. A producer depends on
`lite_sdk2` (the `humanoid_control_msgs` types generated by
[`humanoid_control_msgs_dds`](packages.md#humanoid_control_msgs_dds) plus the DDS channel layer)
rather than hand-writing message mirrors — see
[Talk to Humanoid Control from Python](../how_to/talk_to_humanoid_control_from_python.md). See
[Policy runner](policy_runner.md) for how the in-process learned-policy
path relates.

### `joy_teleop` (gamepad → controller switch)

**NOT a controller plugin** — the stock `joy_teleop` node from ROS
`teleop_tools` (built from source via `humanoid_control.repos`, since
`teleop_tools` isn't in robostack-jazzy). It **replaces** the old
`mode_manager` executable: instead of a state machine, it maps each gamepad
button **directly** to a `/controller_manager/switch_controller` call,
configured entirely by YAML (`lite_joy_teleop.yaml` / `biped_joy_teleop.yaml` /
`prime_joy_teleop.yaml`). The button map follows `qiayuanl/unitree_bringup`'s
`config/g1/joy.yaml`.

Each button **activates one controller and deactivates its siblings**, with
`strictness: BEST_EFFORT`. There is **no gating and no ordering** — any mode
can be entered from any state (e.g. `ZERO_TORQUE → LOCOMOTION` directly, with
no intermediate STANDBY).

**Button map** (per variant; ✓ = bound, — = not present):

| Buttons | Activates | Lite arms | Biped | Prime |
|---|---|---|---|---|
| `X` | `damping_controller` (DAMP) | ✓ | ✓ | ✓ |
| `L1+A` | `standby_controller_a` (STANDBY A) | ✓ | ✓ | ✓ |
| `L1+B` | `standby_controller_b` (STANDBY B) | ✓ | — | ✓ |
| `L1+Y` | `standby_controller_y` (STANDBY Y) | ✓ | — | — |
| `R1+A` | `rl_policy_controller` (LOCOMOTION) | ✓ | ✓ | ✓ |
| `R1+B` | `remote_policy_controller` (REMOTE) | ✓ | — | ✓ |
| `BACK` | *nothing* (STOP — deactivates every mode) | ✓ | ✓ | ✓ |

### STOP

`BACK` activates nothing. Its `switch_controller` request carries only a
`deactivate_controllers` list, so it leaves no mode running and the hardware
holds each joint's safe state: zero stiffness, zero feedforward torque, and the
joint's `safe_damping` on the velocity term (0 by default, so genuinely zero
torque). The drives stay **enabled** — STOP is not a shutdown. CAN `Disable`
still fires on `Ctrl+C` through the hardware's `on_deactivate`.

This is why the robot needs no controller loaded to be safe, and why STOP
cannot fail to find its target.

The request omits `activate_controllers` rather than setting it to `[]`: an
empty list reaches `rcl` as an untyped parameter that `joy_teleop` cannot
declare, which silently kills the node.

Programmatic or headless control skips `joy_teleop` and calls the same service
directly, e.g. `ros2 control switch_controllers --activate standby_controller_a
--deactivate damping_controller`. The currently active mode is read back
from `/controller_manager/list_controllers` (there is no `/control_mode`
topic anymore).

## Spawn order (in launch)

No mode controller is spawned active, so the robot boots into the hardware's
safe state whether or not `joy_teleop` is running
(`enable_joy_teleop:=false` skips it entirely).

| Spawned | State |
|---|---|
| `joint_state_broadcaster` | active |
| `damping_controller`, `standby_controller_{a,b,y}`, `remote_policy_controller` | **inactive** |
| `safety_monitor` | active, after the batch above |
| `rl_policy_controller` | loaded separately by the policy launch |

`safety_monitor` is chained on the inactive batch's exit rather than listed
beside it. Spawners race for a single file lock, so list order does not order
them, and `safety_monitor` can only activate once `damping_controller` — its
fallback — is configured.

## `humanoid_control/SafetyMonitorController`

**Role**: watchdog over the hardware's own health. It reads the `safety_level`
state interface of every component named in its `safety_components` parameter
and claims **no command interface**, so it never competes with a mode
controller and stays active across every switch.

It returns `return_type::ERROR` when any component reports a level at or above
`fault_level`, and also when an interface cannot be read at all — an unknown
level is treated as a fault, because reading it as healthy would defeat the
monitor. That `ERROR` is what triggers the hand-over: the controller_manager
deactivates this controller and activates its `fallback_controllers`.

It publishes nothing. `/safety_status` is a separate telemetry topic, published
by the **hardware component** (`RobstrideSystem`), not by this controller.

`fallback_controllers` must be nested under `controller_manager:` beside the
controller's `type`. Placed anywhere else, `rcl` drops it without complaint and
the fallback is inert. It also fires only on a non-`OK` `update()`; a failing
hardware `read()` or `write()` does not reach it.