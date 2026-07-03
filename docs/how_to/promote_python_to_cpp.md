---
title: Run and extend an in-process policy
---

# Run and extend an in-process policy

Every learned policy on this stack — tracking, piano, locomotion —
runs **in-process** in the C++ `humanoid_control::RLPolicyController` (FSM
`LOCOMOTION` mode). This is the **System 0** real-time layer: inference
happens inside the `ros2_control` RT `update()`, with no allocation, no
blocking, and no separate process that could stall. Policies differ only
by the `.onnx` checkpoint and the `.mcap` motion bag they load; the ONNX
`task_type` metadata selects which observation terms get packed.

This how-to covers the two things a contributor actually needs: how to
**ship** a trained policy onto the robot, and where to add a **new
observation term or task**.

:::note[The old Python-tier promotion workflow was removed]
There used to be an out-of-process Python *inference* tier
(`humanoid_control_policy.remote_policy_runner` / `pianist_policy.PianoPolicyRunner`)
that published `MITCommand` over DDS, plus a "prototype in Python, then
promote to C++" workflow. **That tier is gone.** There is no Python→C++
promotion step anymore — all inference is C++ in-process from the start.
The only Python left on the policy path is the launch-time `prepare`
step (W&B / LeRobot loading, run once at launch, never per tick). See
[Concepts → Software framework](../concepts/architecture.md#policy-execution-system-0-in-process-real-time)
for the full rationale.
:::

## How a policy actually runs

The non-real-time work happens **once at launch** in a `prepare` step;
the RT loop only ever integer-indexes preloaded data.

1. **Launch-time `prepare`.** `ros2 launch humanoid_control_policy lite_policy.launch.py`
   runs `humanoid_control_policy prepare` synchronously. It resolves the ONNX
   checkpoint (a local file or a W&B run), converts the policy's LeRobot
   motion dataset into a single-episode rosbag2 **`.mcap`** motion bag,
   and emits an `rl_policy_controller` parameter overlay
   (`rl_policy_params.yaml`) by transcoding the ONNX
   `custom_metadata_map` — joint order, gains, default pose, action
   scale, `observation_names`, `body_names`, `policy_dt`, `task_type`.
2. **Inactive spawn.** The launch then spawns `rl_policy_controller`
   *inactive* into the running controller_manager with that overlay.
3. **FSM activation.** The operator's `START_LOCOMOTION` intent
   (`/humanoid_control/mode/start_locomotion`, R1+A on the gamepad) activates it.
4. **Per-tick, in-process.** Once active, each RT tick the controller
   packs the observation (`ObservationManager`), runs ONNX inference
   (`OnnxPolicy`), reads the motion reference from the preloaded `.mcap`
   (`ReferenceProvider`), decodes + scatters the action across the full
   articulation (`ActionMapper`), and writes the five MIT command
   interfaces.

The ONNX checkpoint stays the **single source of truth** — `prepare`
transcodes it into the YAML overlay, so "ship a new policy" stays "drop
in the `.onnx`."

## Ship a trained policy

There is no YAML to hand-edit and no ONNX to copy into the workspace.
Point the launch at the checkpoint and let `prepare` do the rest.

First, in one terminal, bring up the controller_manager (sim or
hardware):

```bash
pixi run launch-mujoco        # or: pixi run launch-real
```

Then, in a second terminal (inside `pixi shell`), prepare + load the
policy. From a local ONNX file:

```bash
ros2 launch humanoid_control_policy lite_policy.launch.py \
    checkpoint_file:=/path/to/policy.onnx
```

…or pull it straight from a W&B run:

```bash
ros2 launch humanoid_control_policy lite_policy.launch.py \
    wandb_run_path:=entity/project/run_id
```

Useful extra arguments (all optional):

| Argument | Meaning |
|---|---|
| `wandb_checkpoint_name:=` | Pick a specific ONNX in the W&B run (default: newest `model_*`). |
| `motion_file:=` | Local LeRobot dataset dir override. |
| `registry_name:=` | HuggingFace LeRobot repo id override (the ONNX `dataset_repo_id` wins otherwise). |
| `episode_index:=` | Dataset episode to replay (default `0`). |
| `out_dir:=` | Artifact output dir (default `~/.cache/humanoid_control_policy/launch`). |

For the piano task, use the equivalent
`pianist_policy/launch/piano_policy.launch.py` from `pianist_ros2`; it
runs the same prepare→inactive-spawn flow with the piano metadata.

Finally, drive the FSM to activate (third terminal, inside `pixi shell`):

```bash
ros2 service call /humanoid_control/mode/damp std_srvs/srv/Trigger
ros2 service call /humanoid_control/mode/load_a std_srvs/srv/Trigger  # or load_b for Pose B
# wait for /standby_controller_a/state.is_finished == true (per pose)
ros2 service call /humanoid_control/mode/start_locomotion std_srvs/srv/Trigger
```

:::tip[onnxruntime is opt-in]
`OnnxPolicy` (onnxruntime C++) is only compiled in when onnxruntime is
found at build time — the conda `onnxruntime-cpp` package, already pinned
in `pixi.toml`. Without it the controller loads `PlaceholderPolicy`
instead, which emits **zero actions** — the policy "runs" but does
nothing. The startup log line tells you which backend is active.
:::

## Add a new observation term or task

All term resolution lives in C++ now, in `humanoid_control::ObservationManager`
(`humanoid_controllers/include/humanoid_controllers/observation_manager.hpp`). At
`on_configure` it resolves the metadata-declared `observation_names`
**in order** into a fixed list of term descriptors, then packs them into
a preallocated buffer each tick — no allocation, no string work in the
hot loop. A term resolves to exactly one of three kinds, tried in this
order:

- **Built-in proprioception** — `joint_pos` / `joint_vel` / `actions`
  (with the `(q - q_default) * scale` convention), `imu_quaternion` /
  `imu_angular_velocity` / `imu_linear_acceleration`. Add a new built-in
  by extending the `if/else` chain in `ObservationManager::configure`
  and the `Kind` enum + `switch` in `pack()`.
- **Reference terms served from the `.mcap`** — e.g. tracking's
  `motion_body_pos_b` / `motion_body_ori_b`, piano's `target_keys` /
  `target_keys_future` / `progress`. These come from `ReferenceProvider`
  (`McapTracking` / `McapPiano`). Add a new reference term to the
  matching provider's `resolve()` / `term_dim()` / `get()`, and make
  `prepare` write the data into the `.mcap` motion bag so it's available
  at replay.
- **Extern terms fed by a live topic** — e.g. piano `key_pressed`. The
  controller registers these via `register_extern(name, ptr, dim)`
  *before* `configure()`, pointing at a controller-owned buffer it
  refreshes each tick from a subscription. The live piano key state is a
  generic `std_msgs/Float32MultiArray` (0/1 per key) on `/piano/key_state`
  (published by `piano_state_bridge` in sim, `midi_keyboard_driver` on
  hardware).

So the decision tree for a new term is:

| Your term is… | Add it to… | Plus |
|---|---|---|
| Derived from joint state / IMU | `ObservationManager` built-ins | nothing — proprioception is already local |
| A precomputed time-series from the motion dataset | the relevant `ReferenceProvider` | have `prepare` emit it into the `.mcap` bag |
| A live sensor reading at runtime | a controller `register_extern` + subscription | publish it on a **generic** `Float32MultiArray` topic |

:::tip[Keep `humanoid_controllers` task-agnostic]
Live sensor terms route through a plain `std_msgs/Float32MultiArray`
rather than a task-specific message (no `pianist_msgs` dependency). The
core controller package never learns a specific task exists — it just
packs a named extern vector. A new task adds its own publisher on its
own topic without touching `humanoid_controllers`.
:::

Make sure the new term name appears in the ONNX metadata's
`observation_names` (and, for a new task, set the ONNX `task_type`):
metadata is the source of truth, and `prepare` transcodes it into the
overlay that drives `configure()`.

## When this is *not* the right path

`RLPolicyController` is for **real-time, System-0 dynamical control**
where inference fits cleanly in ONNX Runtime and a stall is unacceptable.

If you have a slow, deliberative, non-real-time source — gravity
compensation today (`Lite-Gravity-Compensation`), VLA / manipulation
later — that belongs in the **System 1/2 external-command ingress**, not
here. Such a source runs out-of-process and publishes `MITCommand` over
DDS to `humanoid_control::RemotePolicyController` (FSM `REMOTE` mode), which validates
joint order, gates on arrival-time staleness, and falls back to damping.
That controller is *not* used by learned policies. See
[Switch controllers without the FSM](./switch_controllers_manually.md)
and the architecture page below.

## See also

- [Concepts → Software framework](../concepts/architecture.md#policy-execution-system-0-in-process-real-time)
  — the System 0 design and the `prepare` → in-process replay flow in full.
- [Concepts → Frozen schemas](../concepts/frozen_schemas.md) — the
  metadata contract (`observation_names`, joint order, scales) the
  checkpoint freezes.
- The C++ controller and modules:
  [`humanoid_controllers/src/rl_policy_controller.cpp`](https://github.com/Berkeley-Humanoids/humanoid_control/blob/main/humanoid_controllers/src/rl_policy_controller.cpp),
  `observation_manager.hpp`, `reference_provider.hpp`, `action_mapper.hpp`,
  `onnx_policy.hpp`.
- The launch:
  [`humanoid_control_policy/launch/lite_policy.launch.py`](https://github.com/Berkeley-Humanoids/humanoid_control/blob/main/humanoid_control_policy/launch/lite_policy.launch.py).
