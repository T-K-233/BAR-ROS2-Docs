# Software framework

This page describes **how the stack runs end-to-end**: the
`ros2_control` cycle (50 Hz on real hardware, 200 Hz in MuJoCo), the
five-mode finite state machine that arbitrates which controller is
active, how policies execute (in-process and real-time — this is the
System 0 layer), the safety / fallback model, and the two-machine
**deployment topology** that decides which of those processes lives on
the robot vs. on the operator workstation.

## Module dependency overview

Before diving into the runtime, here's the static picture — which packages
build against which:

![Module dependency graph](/img/diagrams/concepts__architecture__03_module_deps.svg)

Notice that `humanoid_controllers` does **not** `find_package(humanoid_devices_robstride)`.
The plugin is loaded by `controller_manager` at launch via `pluginlib` — a
runtime dep that doesn't appear in the static graph but is just as binding.
The same applies to every `<plugin>` entry in a controller-manager YAML.

## The ros2_control cycle

`ros2_control` is the integration spine. `controller_manager` owns the
real-time loop. Every tick — 50 Hz on Lite real hardware, 200 Hz in
MuJoCo — it performs three steps:

![ros2_control RT cycle](/img/diagrams/concepts__architecture__01_rt_cycle.svg)

**Constraints inside each phase:**

| Phase | What's allowed | What's forbidden |
|---|---|---|
| `read()` | swap lock-free buffer pointers, copy small POD | syscalls, allocations, DDS waits |
| `update()` | read state_interfaces_, write command_interfaces_, lock-free trylock for diag publishers | allocations, blocking, exceptions across the RT boundary |
| `write()` | stage frames into the bus library's outgoing queue | the actual CAN/EtherCAT syscall (that's the I/O thread's job) |

The I/O thread in each hardware plugin (`humanoid_drivers_socketcan::SocketCanBus`,
`ethercat_driver_ros2`'s EtherLAB master thread) is **separate** from the
controller-manager thread. RT-safety is preserved by making `read()` /
`write()` allocation-free buffer swaps.

### Where the data actually lives

Zooming in on one tick — the path a CAN frame takes from the kernel into a
controller's `update()` and back:

![RT data pipeline](/img/diagrams/concepts__architecture__04_data_pipeline.svg)

The dashed red line is the RT boundary. Anything that crosses it goes
through a **lock-free SPSC ring** — the RT thread can read or stage
frames without ever touching the kernel socket directly. The I/O
thread does the blocking `epoll_wait` and decodes/encodes frames on
its own pace.

Calibration (`direction`, `homing_offset`) is applied **inside** the
plugin's `read()` and `write()`, so every controller above sees joint
frame, never the raw encoder. See [Calibration math](calibration_math.md)
for the formula.

:::tip[Why MIT-mode lives in the hardware plugin, not the controller]
The torque computation
`tau = K_p (q_cmd - q) + K_d (dot q_cmd - dot q) + tau_ff`
runs **on the Robstride motor firmware** (real hardware) or **on MuJoCo's
qfrc_applied step** (sim). The controller just writes five numbers per joint
per tick. This is the same factoring used by MIT Cheetah / Mini Cheetah and
by Berkeley's earlier Humanoid-Control deployment.
:::

## Five-mode finite state machine

The whole control surface boils down to **one active controller at a time**,
selected by `mode_manager`. `joint_state_broadcaster` runs alongside as the
always-on state stream.

![Five-mode FSM](/img/diagrams/concepts__five_mode_fsm__01.svg)

Behavior per state:

| State | Plugin | What it writes |
|---|---|---|
| **ZERO_TORQUE** | `humanoid_control/ZeroTorqueController` | 0 to all 5 cmd interfaces. Startup default, fault fallback. |
| **DAMPING** | `humanoid_control/DampingController` | `K=0`, `D=damping value`, `q_cmd=q_captured` — soft under gravity, resists velocity. |
| **STANDBY** | `humanoid_control/StandbyController` | Linear pose interpolation through a YAML sequence; ramps `K_p / K_d` on first segment. Publishes `StandbyState` with `is_finished`. Two spawned instances of this plugin — `standby_controller_a` (Pose A, `L1+A`) and `standby_controller_b` (Pose B, `L1+B`) — provide two independently selectable poses; from either you can START either policy. |
| **LOCOMOTION** | `humanoid_control/RLPolicyController` | In-process ONNX inference (System 0): packs observations, replays the `.mcap` motion reference, decodes + writes commands — all in the RT `update()`. Runs every learned policy (tracking / piano / locomotion); they differ only by the loaded `.onnx` + `.mcap`. |
| **REMOTE** | `humanoid_control/RemotePolicyController` | System 1/2 external-command ingress: subscribes `~/command` (`MITCommand` over DDS) from a *non*-real-time source (gravity-comp today, VLA / manipulation later) with arrival-time stale-command gating. |

### Transition mechanics

Every transition is **one `switch_controller` service call** to the
controller_manager (STRICT strictness, async). The `mode_manager` node is a
plain `rclcpp::Node` that subscribes:

- `/joy` (gamepad intents; on by default — bringup hard-fails if `/dev/input/js*`
  is missing unless you opt out with `enable_gamepad:=false`)
- `/standby_controller_a/state` and `/standby_controller_b/state` (one per standby pose; the `is_finished` gate for the two `START_*` intents)
- `/safety_status` (the auto-DAMP trigger)

…and exposes six `std_srvs/Trigger` services so transitions can also be
driven from the command line:

- `/humanoid_control/mode/damp`, `/humanoid_control/mode/load_a`, `/humanoid_control/mode/load_b`,
  `/humanoid_control/mode/start_remote`, `/humanoid_control/mode/start_locomotion`,
  `/humanoid_control/mode/quit`

`/control_mode` is published at 50 Hz. The manager polls
`list_controllers` periodically (every 25 ticks = 500 ms) so controllers
loaded after the first poll become visible to `dispatch_intent` without
the operator having to re-trigger.

## Policy execution: System 0 (in-process, real-time)

Robot control is often split across three timescales — **System 2**
(slow deliberation: VLM/VLA planning), **System 1** (fast reactive
policy), and **System 0** (the lowest-level real-time motor loop). This
stack *is* System 0. Its defining constraint: the policy must run inside
the `ros2_control` RT cycle with no allocation, no blocking, and no
dependence on a separate process that could stall.

So every learned policy — tracking, piano, locomotion — runs
**in-process** in `RLPolicyController`. Each tick the controller packs
the observation (`ObservationManager`), runs ONNX inference
(`OnnxPolicy`), reads the motion reference from a preloaded `.mcap`
(`ReferenceProvider`), decodes the action and scatters it across the
full articulation (`ActionMapper`), and writes the five MIT command
interfaces — all without leaving the RT thread.

![Policy execution: System 0 in-process controller, the launch-time prepare step, and the System 1/2 ingress](/img/diagrams/concepts__architecture__02_policy_tiers.svg)

:::tip[Why not an out-of-process Python policy?]
An earlier design ran inference in a Python `rclpy` node that streamed
`MITCommand` over DDS. Convenient — Python owns the W&B / LeRobot / ONNX
ecosystem — but it cannot offer a real-time guarantee: a GC pause, a
scheduler hiccup, or one dropped DDS packet stalls the command stream,
and the controller can only fall back to a passive hold. For a System-0
loop that is the wrong trade. The *only* reason the Python tier existed
was its dependencies, so we moved the **dependencies** off the hot path
rather than the **inference**.
:::

### Launch-time `prepare`, then in-process replay

The heavy, non-real-time work runs **once at launch**, never per tick.
`humanoid_control_policy prepare` (and `pianist_policy prepare`) resolves the ONNX
checkpoint (local file or W&B run) and converts the policy's LeRobot
motion dataset into a single-episode rosbag2 **`.mcap`** bag, then emits
an `rl_policy_controller` parameter overlay. The launch runs `prepare`
synchronously, loads `rl_policy_controller` *inactive* with the overlay,
and the operator's `START_LOCOMOTION` activates it.

:::tip[Why `.mcap`, and why the ONNX stays the source of truth]
`.mcap` is the lab's format for handing data to C/C++: it reads cleanly
from `rosbag2_cpp` with stock `std_msgs/Float32MultiArray` — no custom
message package, no parquet/HuggingFace dependency in the controller.
The controller loads every frame at `on_configure` (non-RT) and
integer-indexes them per tick. And nothing about the policy is
hand-restated in YAML: `prepare` transcodes the ONNX `custom_metadata_map`
(joint order, gains, default pose, action scale, observation term names,
`policy_dt`, body names) into the overlay, so the **checkpoint stays the
single source of truth** and "ship a new policy" stays "drop in the
`.onnx`."
:::

### Observation packing (in C++)

`ObservationManager` packs the metadata-declared `observation_names`
**in order** into a preallocated buffer (no allocation, no string work in
the hot loop), resolving each term as one of:

- **built-in proprioception** — `joint_pos` / `joint_vel` / `actions`
  (scaling `out = (q - q_default) * scale`), `imu_quaternion` /
  `imu_angular_velocity` / `imu_linear_acceleration`;
- **reference terms** served from the `.mcap` — `motion_body_pos_b` /
  `motion_body_ori_b` (tracking); `target_keys` / `target_keys_future` /
  `progress` (piano);
- **extern terms** fed by a live topic — piano `key_pressed`, a generic
  `std_msgs/Float32MultiArray` on `/piano/key_state` (published by
  `piano_state_bridge` in sim, `midi_keyboard_driver` on hardware).

:::tip[Why a *generic* topic for the live key state]
Routing live key state through a plain float array — rather than
`pianist_msgs/PianoKeyState` — keeps `humanoid_controllers` free of any
task-package dependency. The core controller package never learns the
piano task exists; it just packs a named extern vector. New tasks add
their own publisher on their own topic without touching `humanoid_controllers`.
:::

`reset()` (on activation) and `record_action()` (once per tick, after
inference) advance the reference frame exactly once per policy step,
matching the training-time convention.

### System 1/2 ingress

`RemotePolicyController` is retained for the genuinely non-real-time
sources that *should* live out-of-process: it subscribes to `MITCommand`
over DDS and writes the bus, with arrival-time staleness gating. Today
that is the gravity-compensation runner (`Lite-Gravity-Compensation` —
raw CycloneDDS, no `rclpy`); next it is VLA / manipulation. Such a client
does not hand-write the message types: [`humanoid_control_msgs_dds`](../reference/packages.md#humanoid_control_msgs_dds)
generates wire-compatible `cyclonedds` types from `humanoid_control_msgs/msg/*.msg`, and
the `lite_sdk2` SDK wraps them in a publisher/subscriber layer — see
[Talk to Humanoid Control from Python](../how_to/talk_to_humanoid_control_from_python.md).
These are System 1/2: slower, deliberative, and tolerant of the latency the
DDS hop adds.

`MITState` is a **code-level** schema (a `humanoid_control::MITState` POD in
`humanoid_control_common`) — not a published topic. Observations are assembled
in-process from `/lite/joint_states` (the always-on broadcaster) and
`/imu/data` (the IMU driver). See [Policy runner](../reference/policy_runner.md).

## Frozen schemas

A handful of artifacts are **frozen once a trained policy depends on them**:

| Artifact | Frozen because |
|---|---|
| `humanoid_control_msgs/MITCommand` | trained policies emit this field-by-field over DDS |
| Joint order in `humanoid_control_*_controllers.yaml` | trained policies index into this order |
| `MITState` struct + Python dataclass | both sides agree on `joint_position`/`joint_velocity`/IMU layout |
| Observation term scale + default vectors | shifts mean retraining |

Once a policy ships to a piano-playing or locomotion run, changing any of
these forces retraining. Keep this in mind when refactoring.

## Safety and fault handling

Safety is **layered** — no single ROS node is treated as the whole safety
system:

Concrete examples:

- A Robstride bus-off → `humanoid_devices_robstride` publishes `SafetyStatus{level=FAULT,
  source="humanoid_devices_robstride/can0", flags=BUS_OFF}` → `mode_manager` requests a
  STRICT switch to DAMPING. If DAMPING fails (e.g. command interfaces
  unavailable), `mode_manager` falls back to ZERO_TORQUE.
- A `RemotePolicyController` whose Python publisher stalls for >100 ms
  (`stale_command_timeout_ms` default) falls into a **damped hold** by
  default (`stale_command_policy: passive` → zero stiffness, high damping
  like DAMPING mode, holding the live joint position — the arms stay
  damped, not limp), or zero-order-holds the last command if
  `stale_command_policy: hold` is set. Staleness is measured against
  **arrival time at the subscription callback**, not against
  `MITCommand.header.stamp`, so publisher clock skew is irrelevant.
- An RL policy returning NaN in its action vector → `RLPolicyController`
  detects via `humanoid_control::rt::all_finite(...)` and returns `return_type::ERROR`,
  triggering `fallback_controllers` in the CM YAML.

## Deployment topology

The shipping configuration is a **two-machine tethered split**. The
same colcon workspace is installed (and built from the same pixi lock
file) on both machines; each launch boots only the subset of nodes
that belongs on its side. Single-machine sim/dev paths
(`humanoid_bringup_lite/mujoco.launch.py`, `humanoid_bringup_lite/view_lite.launch.py`,
`humanoid_bringup_lite/calibrate.launch.py`) are unaffected — they
collapse both sides into one process tree.

Launches come from two sibling repos: `Humanoid Control` ships every
Lite/Prime control-plane and tracking-policy launch; `pianist_ros2`
ships the piano-task-specific launches.

| Side | Machine | Launch | What lives here |
|---|---|---|---|
| **Robot** | Onboard computer (RT kernel, wired tether) | `humanoid_bringup_lite/launch/real.launch.py` (Humanoid Control) | `ros2_control_node`, `humanoid_devices_robstride` / `humanoid_devices_sito` hardware plugins, `joint_state_broadcaster`, the six FSM controllers (`zero_torque` / `damping` / `standby_a` / `standby_b` / `rl_policy` / `remote_policy`), `mode_manager`, `joy_node`, `robot_state_publisher`, IMU driver |
| **Host** | Operator workstation | `humanoid_bringup_lite/launch/viz.launch.py` (Humanoid Control) | `viser_viz` *or* `rerun_viz` (selected by `viewer:=`) |
| **Robot** | Onboard computer | `humanoid_control_policy/launch/lite_policy.launch.py` (Humanoid Control) / `pianist_policy/launch/piano_policy.launch.py` (pianist_ros2) | Runs `prepare` (resolve ONNX, convert motion → `.mcap` + overlay) then loads `rl_policy_controller` into the local CM. Inference is in-process, so the `.onnx` / `.mcap` artifacts **and** the W&B / HF Hub / `onnxruntime` *prepare-time* deps live here. The RT path itself pulls none of them. |
| **Robot** | Onboard computer | `pianist_policy/launch/midi_keyboard_driver.launch.py` (pianist_ros2) | USB-MIDI keyboard driver → `/piano/key_state` (`std_msgs/Float32MultiArray`); feeds the on-robot controller's `key_pressed` extern term locally (loopback, does **not** cross the tether). |

:::tip[The deployment trade the in-process move makes]
Out-of-process inference kept the heavy ML deps on the host and streamed
commands over the tether. In-process inference flips that: the heavy deps
move onto the robot — but only for the **one-shot `prepare` step at
launch**, never the RT loop — and the single RT-adjacent host→robot stream
disappears. A flaky tether can no longer stall the command stream, because
there is no command stream to stall. The host is left with viz only (and,
optionally, a System 1/2 source publishing `MITCommand` to
`RemotePolicyController`).
:::

### What crosses the tether

Only DDS topics, never controller-manager service calls.

| Topic | Direction | QoS | Rate / size | Notes |
|---|---|---|---|---|
| `/robot_description` | robot → host | RELIABLE + TRANSIENT_LOCAL | ~kB, latched | URDF tree (no meshes — host has its own install share). |
| `/lite/joint_states` | robot → host | RELIABLE | 50 Hz, ~14 floats × 3 | Viewer input. The in-process policy reads it locally on the robot, so it no longer feeds a host process on the policy path. |
| `/imu/data` | robot → host | RELIABLE | sensor-rate | Viewer / System 1/2 input. The in-process policy reads it locally on the robot. |
| `/control_mode` | robot → host | RELIABLE | 50 Hz | FSM telemetry for operator dashboards. |
| `/remote_policy_controller/command` | host → robot | RELIABLE depth 4 | ~280 B | *Only* present when a System 1/2 source runs off-robot (gravity-comp, future VLA). `RemotePolicyController` uses arrival-time staleness, not header.stamp. The learned policy no longer uses this path — it runs in-process. |
| `/tf` | robot → host | RELIABLE | 50 Hz | RSP fanout — viewers consume. |

`/joy` (gamepad) and `/safety_status` are intentionally onboard-only:
both go straight into `mode_manager` (loopback) so the safety path
never depends on the tether. `/piano/key_state` is robot-local
(MIDI driver / sim bridge → the in-process controller's `key_pressed`
term), so it does not cross the tether either.

### Why this split (the three judgment calls)

- **Gamepad on the robot.** `DAMP` and `QUIT` are the operator's
  safety affordance. Routing `/joy` over DDS across the tether means
  a flaky link can suppress an e-stop. Every legged-RL deployment
  this project mirrors (`legged_control2`, `instinct_onboard`, the
  earlier Humanoid-Control stack) keeps the gamepad onboard. Use a
  USB extension or a wireless dongle plugged into the onboard
  computer, not into the host laptop.
- **`mode_manager` on the robot.** It calls
  `/controller_manager/switch_controller` (a service local to CM)
  and consumes `/safety_status` from the per-bus hardware plugins.
  Placing it onboard makes switch-controller, safety auto-DAMP, and
  `/joy` consumption all loopback — zero cross-machine latency in
  the safety path.
- **`robot_state_publisher` on the robot.** RSP is a pure transform
  fanout. Putting it onboard means `/robot_description` (latched)
  and `/tf` originate at one address; host-side viewers subscribe
  over the wire. Bandwidth is small (kinematic tree, not point
  clouds).

### Network assumptions

- **Wired Ethernet tether only.** WiFi as the operator-to-robot
  link is explicitly not supported; if the requirement appears,
  gamepad-on-robot is doubly justified and DDS QoS needs separate
  tuning.
- Both machines run the same `ROS_DOMAIN_ID` and (recommended) the
  same `RMW_IMPLEMENTATION`. Cyclone DDS is the recommended pick;
  pin the network interface in the XML config so discovery doesn't
  leak onto management NICs.

AGENTS.md §"Deployment topology" carries the canonical version of
this split (with an ASCII process diagram); this page reflects the
deployed surface.

## Next

- [`mode_manager` source](https://github.com/Berkeley-Humanoids/humanoid_control_ros2/blob/main/humanoid_controllers/src/mode_manager.cpp)
  — the FSM is ~150 lines of C++; readable in one sitting.
- [Lite 101](../getting_started/lite_101.md) — see all of this run end-to-end
  against mock hardware and MuJoCo.
- [Controllers reference](../reference/controllers.md) — per-controller
  parameter tables.