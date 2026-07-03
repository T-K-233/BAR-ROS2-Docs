# Controllers + FSM

Five `controller_interface::ControllerInterface` plugins, one standalone
`rclcpp::Node` orchestrator. **Only one mode controller is active at a time**;
`joint_state_broadcaster` runs always.

## FSM summary

See [Concepts → Architecture](../concepts/architecture.md#five-mode-finite-state-machine)
for the annotated version including safety-fault edges.

## Plugin-by-plugin

### `humanoid_control/ZeroTorqueController`

**Role**: startup default; safer fault fallback.

**Claims**: position, velocity, effort, stiffness, damping on every joint.

**Writes** every tick: `0` to all 5 command interfaces.

**Parameters**:

| Param | Type | Default | Description |
|---|---|---|---|
| `joints` | `string[]` | — | Required. Joint names to claim (must match URDF). |

### `humanoid_control/DampingController`

**Role**: compliant fail-safe. The robot stays **soft under gravity** but
**resists velocity**.

**Mechanics**: on `on_activate`, captures the current joint positions into
`captured_position_`. Every tick writes:

| Interface | Value |
|---|---|
| `position` | `captured_position_[i]` |
| `velocity` | `0` |
| `effort`   | `0` |
| `stiffness`| `0` |
| `damping`  | `damping_value_[i]` |

With `stiffness = 0`, no restoring force; with `damping > 0`, viscous
resistance.

**Parameters**:

| Param | Type | Default | Description |
|---|---|---|---|
| `joints` | `string[]` | — | Required. |
| `damping` | `float64[]` | `[]` | Per-joint damping. Empty → use `damping_scalar`. |
| `damping_scalar` | `float64` | `1.0` | Used when `damping` is empty. |

### `humanoid_control/StandbyController`

**Role**: linearly interpolate joint positions through a pose sequence; ramp
`K_p / K_d` from `0` to target gains during the **first** segment so
activation never snaps.

**Instances**: spawned **twice** — `standby_controller_a` (Pose A, loaded by
`L1+A` / `/humanoid_control/mode/load_a`) and `standby_controller_b` (Pose B,
loaded by `L1+B` / `/humanoid_control/mode/load_b`). Same plugin class (and same
`standby_controller.cpp`), different pose parameters in the bringup YAML.

**Parameters**:

| Param | Type | Description |
|---|---|---|
| `joints` | `string[]` | Required. |
| `target_stiffness` | `float64[]` | Per-joint target `K_p` when ramp finishes. |
| `target_damping` | `float64[]` | Per-joint target `K_d`. |
| `segment_durations` | `float64[]` | Seconds per pose segment. Length determines how many pose segments are expected. |
| `pose_segment_<i>` | `float64[]` | Per-segment target pose vector; one parameter per segment index in `[0, len(segment_durations))`. Each is a per-joint position array sized to `len(joints)`. |

**Publishes**: `~/state` (`humanoid_control_msgs/StandbyState`) with `TRANSIENT_LOCAL` QoS
so `mode_manager` sees `is_finished` even on late join — i.e.
`/standby_controller_a/state` and `/standby_controller_b/state`, one per instance.
Watch the one matching the pose you loaded.

:::tip[How the bundled config interpolates]
`humanoid_control_lite_controllers.yaml` configures **both instances** with
**two segments** each: `pose_segment_0` is the zero-pose (where the robot
starts) and `pose_segment_1` is that instance's target pose —
`standby_controller_a` and `standby_controller_b` differ only in this final
pose (Pose A vs Pose B). A LOAD_A / LOAD_B intent therefore animates the arms
from zero to the chosen pose over two 2-second segments while ramping `K_p` /
`K_d` from 0 to the target gains during the first segment.
:::

`fallback_controllers: ["damping_controller"]` is set on the
controller-manager side so any non-`OK` `return_type` from `update()`
auto-deactivates Standby and activates Damping.

### `humanoid_control/RLPolicyController`

**Role**: **in-process** ONNX inference — this is the System 0 path that
runs *every* learned policy (tracking / piano / locomotion). Each RT
`update()` it packs the observation (`ObservationManager`), runs inference
(`OnnxPolicy`), reads the motion reference from the preloaded `.mcap`
(`ReferenceProvider`), maps the action across the full articulation
(`ActionMapper`), and writes the five MIT command interfaces — never
leaving the RT thread. Policies differ only by the loaded `.onnx` +
`.mcap`; the ONNX `task_type` metadata selects the term set.

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
back to `PlaceholderPolicy` (zeros) — useful for smoke-testing the FSM and
the observation/reference plumbing without a real inference dependency.
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
| `stale_command_policy` | `string` | `passive` | `passive` or `hold`. `passive` is a **damped hold** — zero stiffness (`kP=0`) and high damping (`kD = damping_scalar`) while holding the live joint position, exactly like DAMPING mode; applied both on entering REMOTE before the first command **and** on stale dropouts (it no longer goes fully limp). `hold` is unchanged. |
| `stale_command_timeout_ms` | `int` | `100` | Staleness window measured against the message's **arrival time at the subscription callback**, not against `MITCommand.header.stamp`. Publisher clock skew is irrelevant. |
| `damping` | `float64[]` | `[]` | Per-joint `K_d` for the `passive` damped hold. Empty → use `damping_scalar`. |
| `damping_scalar` | `float64` | `6.0` | Damping used when `damping` is empty — matches the DAMPING mode's damping. |

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

### `mode_manager` (executable)

**NOT a controller plugin** — a regular `rclcpp::Node` compiled as the
`humanoid_controllers/mode_manager` executable.

| Input | Topic / source | Purpose |
|---|---|---|
| Gamepad | `/joy` (`sensor_msgs/Joy`) | DAMP / LOAD / START_LOCOMOTION / START_REMOTE / QUIT intents |
| Standby done | `/standby_controller_a/state` or `/standby_controller_b/state` (`StandbyState`) | gate the START intents on `is_finished` (watch the loaded pose's instance) |
| Safety | `/safety_status` (`SafetyStatus`) | auto-fall to DAMPING on non-OK |
| Trigger services | `/humanoid_control/mode/{damp,load_a,load_b,start_remote,start_locomotion,quit}` (`std_srvs/Trigger`) | same intents from the command line |

| Output | Topic | Purpose |
|---|---|---|
| FSM state | `/control_mode` (`ControlMode`) | 50 Hz telemetry |
| Mode switch | `/controller_manager/switch_controller` | the actual transition |

**Joy bindings** (Xbox-layout defaults — remap via the `joy.*` params):

| Buttons | Intent | Target |
|---|---|---|
| `X` (2) | DAMP | `damping_controller` |
| `L1+A` (4+0) | LOAD_A | `standby_controller_a` (Pose A) |
| `L1+B` (4+1) | LOAD_B | `standby_controller_b` (Pose B) |
| `R1+A` (5+0) | START_LOCOMOTION | `rl_policy_controller` |
| `R1+B` (5+1) | START_REMOTE | `remote_policy_controller` |
| `BACK` (6) | QUIT | `rclcpp::shutdown()` |

The two LOAD combos load **different poses** (`standby_controller_a` vs
`standby_controller_b`); the two START combos pick the **policy**. The two
axes are independent — from either standby pose you can start either policy
(`R1+A` → LOCOMOTION, `R1+B` → REMOTE), so `L1+A → R1+B` is just as valid as
`L1+A → R1+A`. The only constraint is that you cannot switch A↔B directly:
`LOAD` is admissible only from DAMPING, so to change pose you DAMP first,
then load the other pose.

**Parameters**:

| Param | Type | Default | Description |
|---|---|---|---|
| `tick_rate_hz` | `float64` | `50.0` | timer rate |
| `controller_manager` | `string` | `/controller_manager` | CM namespace |
| `joy.damp_button` | `int` | `2` | DAMP button index |
| `joy.quit_button` | `int` | `6` | QUIT button index |
| `joy.load_combo_a` | `int[]` | `[4, 0]` | LOAD_A combo (L1+A → Pose A) |
| `joy.load_combo_b` | `int[]` | `[4, 1]` | LOAD_B combo (L1+B → Pose B) |
| `joy.start_combo_locomotion` | `int[]` | `[5, 0]` | START_LOCOMOTION combo (R1+A) |
| `joy.start_combo_remote` | `int[]` | `[5, 1]` | START_REMOTE combo (R1+B) |

## Spawn order (in launch)

The launch spawns `zero_torque_controller` active independently — so even if
`mode_manager` dies, the robot is in the safe state.