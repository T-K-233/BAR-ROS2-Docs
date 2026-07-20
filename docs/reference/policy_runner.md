# Policy runner

The learned policy runs **in-process** in `humanoid_control::RLPolicyController` (C++,
real-time — the System 0 path). What "policy runner" used to mean — a
Python `rclpy` node streaming `MITCommand` over DDS — is gone. Its
dependency-heavy work now happens in a launch-time `prepare` step, and
inference happens inside the controller. This page documents that split:
the `prepare` CLI, the ONNX metadata schema (the
training↔deployment contract, unchanged), and the in-process
observation-term registry.

:::note[Migrated from the out-of-process runner]
Earlier docs described `humanoid_control_policy.remote_policy_runner` and a
`pianist_policy.PianoPolicyRunner` subclass publishing over DDS. Those are
removed. `humanoid_control_policy` is now a launch-time **prep tool**, inference is
in-process in `RLPolicyController`, and `RemotePolicyController` remains
only as the System 1/2 external-command ingress (gravity-comp, future
VLA). See [Architecture › Policy execution](../concepts/architecture.md).
:::

## Why "self-describing ONNX"

The training pipeline writes 13 fields into the ONNX file's
`custom_metadata_map` at export time — joint order, per-joint PD gains,
default pose, action scale, observation term names, body names, the
LeRobot dataset id, the policy tick period. `prepare` parses those fields
into a typed `PolicyMetadata` object and **transcodes them into the
`rl_policy_controller` parameter overlay** — the controller never relies
on a hand-written YAML to restate them. The overlay is machine-generated
from the checkpoint, so the `.onnx` stays the single source of truth.

This matters because **any mismatch between the training-time graph and
the deployment-time config breaks the policy silently** (wrong joint order
or off-by-one observation slice will still produce well-shaped tensors
that just behave terribly). Embedding the metadata in the ONNX file means
training and deployment cannot drift independently.

## Composition

**Launch-time `prepare`** (Python, `humanoid_control_policy` / `pianist_policy`):

| Module | Responsibility |
|---|---|
| `checkpoint_loader.resolve_checkpoint` | Resolve a local path or a W&B run (`entity/project/run_id`) to a local `.onnx`; cache under `~/.cache/humanoid_control_policy/wandb/<run_id>/`. |
| `policy_metadata.load_policy_metadata` | Parse `custom_metadata_map` → frozen `PolicyMetadata`. Helpers `joint_stiffness_map()`, `default_joint_pos_map()`, `action_scale_map()` return `dict[str, float]` keyed by joint name. |
| `convert.tracking_frames` / `pianist_policy.prepare.piano_frames` | Read the LeRobot episode and emit per-frame arrays (tracking: `[pos·3B][ori6d·6B]`; piano: `[key_pressed·K]`). |
| `mcap_writer.write_motion_bag` | Write those frames to a single-episode rosbag2 `.mcap` bag (`std_msgs/Float32MultiArray`, via `rosbag2_py`). |
| `prepare.write_param_overlay` | Emit `rl_policy_params.yaml` — the metadata transcoded into `rl_policy_controller` params (joints, gains, scale, obs names, `motion_file`, `policy_checkpoint`, …). |

**Runtime** (in-process, C++ `humanoid_controllers`):

| Module | Responsibility |
|---|---|
| `OnnxPolicy` | onnxruntime **C++** session. Single-step inference, shape contract `float32 (1, N) -> float32 (1, M)`. (Opt-in: needs the conda `onnxruntime-cpp` package, pinned in `pixi.toml`; else falls back to `PlaceholderPolicy`.) |
| `ObservationManager` | Resolves each name in `observation_names` to a term via three-stage lookup — built-in proprioception → reference provider → topic-fed extern — and packs them into a preallocated buffer each tick (no allocation / no string work in the hot loop). Owns reference lifecycle (`reset` on activation, `step` after each `record_action`). |
| `ReferenceProvider` (`McapTrackingReference` / `McapPianoReference`) | Loads the `.mcap` whole at `on_configure`; integer-indexes per tick to serve `motion_body_pos_b` / `motion_body_ori_b` (tracking) or `target_keys` / `target_keys_future` / `progress` (piano). |
| `ActionMapper` | `pos = default + action * scale` per action joint, scattered into the full articulation; undriven joints (not in `action_joint_names`) pinned to `position=0` with the policy's `K`/`D`. |

## ONNX metadata schema

The 13 required keys (parsed from `session.get_modelmeta().custom_metadata_map`):

| Key | Type | Meaning |
|---|---|---|
| `task_type` | `"tracking"` \| `"piano"` \| `"locomotion"` | Selects the reference provider class. |
| `joint_names` | `tuple[str, ...]` | Full articulation list (17 for Lite). Indexes `joint_stiffness`, `joint_damping`, `default_joint_pos`. |
| `action_joint_names` | `tuple[str, ...]` | The subset the policy actually emits actions for. Joints in `joint_names` but not here are "undriven" and get pinned to zero. |
| `joint_stiffness` | `tuple[float, ...]` | Per-joint `K_p`, aligned to `joint_names`. |
| `joint_damping` | `tuple[float, ...]` | Per-joint `K_d`, aligned to `joint_names`. |
| `default_joint_pos` | `tuple[float, ...]` | Per-joint default position (the `q_default` in `out = (q - q_default) * scale`). |
| `observation_names` | `tuple[str, ...]` | The flat observation vector, term by term. See [Observation term registry](#observation-term-registry). |
| `command_names` | `tuple[str, ...]` | Future-use; runtime command terms (e.g. velocity targets) that aren't part of the proprio observation. |
| `action_scale` | `float` \| `tuple[float, ...]` | Per-action-joint scale. Scalar broadcasts across all joints. |
| `policy_dt` | `float` | Policy tick period in seconds. The runner uses this for its `create_timer` unless `policy_dt_override` is set. |
| `body_names` | `tuple[str, ...]` | Reference-tracked bodies (for `motion_body_pos_b` / `motion_body_ori_b` terms). |
| `dataset_repo_id` | `str` | Default HF repo id for the reference dataset; overridable at launch. |
| `lookahead_steps` | `tuple[int, ...]` | Piano-only: frame offsets the policy was trained to look ahead at. |

## Observation term registry

`observation_names` is a CSV like
`motion_body_pos_b, motion_body_ori_b, joint_pos, joint_vel, actions`
(tracking task) or
`target_keys, progress, key_pressed, joint_pos, joint_vel, actions`
(piano task). Names match upstream pianist-tracking-mj actor terms
directly. The C++ `ObservationManager` resolves each name to one of three
sources, in this order:

1. **Built-in proprioception** — packed directly from the current
   `MITState`:

   | Name | Slice from |
   |---|---|
   | `joint_pos` | `(state.joint_position - default) * scale` |
   | `joint_vel` | `state.joint_velocity` |
   | `actions` | last action recorded via `record_action()` |
   | `imu_quaternion` | `state.imu_quat` `(w, x, y, z)` |
   | `imu_angular_velocity` | `state.imu_gyro` |
   | `imu_linear_acceleration` | `state.imu_accel` |

2. **Reference-provider terms** — served from the preloaded `.mcap` by
   the attached `ReferenceProvider`, selected by `task_type`:
   - `McapTrackingReference` (`task_type='tracking'`):
     `motion_body_pos_b`, `motion_body_ori_b`.
   - `McapPianoReference` (`task_type='piano'`):
     `target_keys`, `target_keys_future`, `progress`.
     (`target_keys_future` is the K-frame lookahead; upstream
     `piano_env_cfg` currently keeps it commented out, so its slot in
     `observation_names` is conditional on the trained policy.)

3. **Topic-fed extern terms** — filled from a live subscription. Piano's
   `key_pressed` reads a generic `std_msgs/Float32MultiArray` on
   `/piano/key_state` (published by `piano_state_bridge` in sim,
   `midi_keyboard_driver` on hardware). This keeps `humanoid_controllers` free
   of any `pianist_msgs` dependency.

Unknown names fail at `on_configure` — the guarantee is that **every
observation slot has a deterministic source** before the controller goes
active.

## Launch flow: `prepare` then spawn

There is no runner process. The launch (`humanoid_control_policy/launch/lite_policy.launch.py`,
or `pianist_policy/launch/piano_policy.launch.py` for piano) does two
things, in order:

1. **Runs `prepare` synchronously** — a one-shot `ros2 run humanoid_control_policy
   prepare` (`ros2 run pianist_policy prepare` for piano) that resolves
   the ONNX, writes the `.mcap` motion bag, and emits the
   `rl_policy_params.yaml` overlay. This is the dependency-heavy,
   non-real-time work; it must finish before the controller configures.
2. **Spawns `rl_policy_controller` *inactive*** with the overlay as a
   `--param-file`. The operator activates it **directly** — there is no
   FSM and no soft-start gating, so the transition is allowed from any
   state: `ros2 control switch_controllers --activate rl_policy_controller
   --deactivate standby_controller_a` (or whichever controller is active).
   On the gamepad that is R1+A, which `joy_teleop` maps straight to
   `/controller_manager/switch_controller`.

The launch args are pass-throughs to the `prepare` CLI below (plus
`out_dir`, defaulting to `~/.cache/humanoid_control_policy/launch/`, which fixes the
overlay path the spawner reads).

### `prepare` CLI args

`ros2 run humanoid_control_policy prepare` (console script `prepare =
humanoid_control_policy.prepare:main`); `pianist_policy prepare` is the piano
counterpart and adds the last two:

| Arg | Default | Effect |
|---|---|---|
| `--checkpoint-file` | (empty) | Path to a local `.onnx`. Mutually exclusive with `--wandb-run-path`. |
| `--wandb-run-path` | (empty) | W&B run path (`entity/project/run_id`); the ONNX is downloaded and cached at `~/.cache/humanoid_control_policy/wandb/<run_id>/`. |
| `--wandb-checkpoint-name` | (empty) | Specific `.onnx` filename inside the W&B run (default: newest `model_*`). |
| `--motion-file` | (empty) | Local LeRobot dataset dir. Wins over registry and the ONNX-baked repo id. |
| `--registry-name` | (empty) | HF repo id to use instead of the ONNX-baked `dataset_repo_id`. Useful when iterating on dataset variants. |
| `--episode-index` | `0` | Reference-dataset episode index to convert. |
| `--out-dir` | `~/.cache/humanoid_control_policy/artifacts/<stem>` | Where the `.onnx` copy, `.mcap` bag, and overlay are written. |
| `--skip-stride` | `1` | Piano-only: stride between lookahead frames (the training-time value). |
| `--key-state-topic` | `/piano/key_state` | Piano-only: the live key-state topic (`std_msgs/Float32MultiArray`) the controller subscribes to. |

Argument names match mjlab's `play` CLI vocabulary so the same string
moves between training-time and deployment-time scripts.

The launch arguments use the same names without the `--` and with
underscores (`checkpoint_file`, `wandb_run_path`, …) and are forwarded
verbatim to the CLI.

## Dataset resolution order

`prepare` picks the reference dataset source in this priority:

1. **`--motion-file <local path>`** — air-gapped deployments pre-fetch via
   `hf download` and point here.
2. **`--registry-name <hf_repo_id>`** — for testing alternative
   datasets without re-exporting the ONNX.
3. **`PolicyMetadata.dataset_repo_id`** — the default. First run will
   download from Hugging Face Hub.

Logged to stderr at prepare-time so you always know which one was used.

## Piano is a different ONNX `task_type`, not a subclass

There is no runner to subclass. The piano task is just a checkpoint whose
ONNX metadata carries `task_type='piano'`, prepared by the
`pianist_policy prepare` tool (it owns the MIDI/song → key-state `.mcap`
conversion and the piano overlay). At runtime the same in-process
`RLPolicyController` loads it; the `task_type` metadata selects the
`McapPianoReference` provider over `McapTrackingReference`, and the
piano-only observation terms (`target_keys`, `progress`, `key_pressed`)
resolve through that provider and the live `/piano/key_state` extern.
`humanoid_controllers` never learns the piano task exists.

New task families follow the same pattern: a sibling `<task>_ros2` repo
ships a `<task>_policy prepare` tool that emits the overlay + `.mcap`; the
shared C++ controller dispatches on `task_type`.

## Per-tick flow (in-process, RT)

Inside `RLPolicyController::update()` — no process boundary, no DDS hop:

1. **Build the observation.** `ObservationManager` packs every name in
   `observation_names` (in order) into the preallocated input buffer,
   resolving each against the current `MITState` (refreshed from
   `/lite/joint_states` + `/imu/data`), the reference frame from the
   `.mcap` provider, and any topic-fed extern (e.g. `/piano/key_state`).
2. **Run inference.** `OnnxPolicy` runs the forward pass on the flat
   observation vector (or `PlaceholderPolicy` returns zeros when
   `onnxruntime-cpp` isn't built in).
3. **Map the action.** `ActionMapper` computes
   `pos = default + action * scale` per action joint, scatters it across
   the full articulation, and writes the five MIT command interfaces with
   the policy's `K`/`D`; undriven joints get `position=0`.
4. **Advance the reference.** `record_action` refreshes the
   last-action term and steps the provider so the `.mcap` frame advances
   exactly once per policy step.

The step ordering keeps the policy from observing the *post-action*
reference frame on the same tick it commanded against — every tick is
`(t, t+1)` in the dataset, never `(t+1, t+1)`. Non-finite observations or
actions trip `humanoid_control::rt::all_finite(...)` and return `return_type::ERROR`,
triggering the CM `fallback_controllers`.

## See also

- [`humanoid_control/RemotePolicyController`](controllers.md#barremotepolicycontroller)
  — the **System 1/2 external-command ingress** (gravity-comp today, VLA
  later); no longer part of the learned-policy path.
- [Architecture › Policy execution: System 0](../concepts/architecture.md#policy-execution-system-0-in-process-real-time)
  — the in-process, real-time framing this page implements.
