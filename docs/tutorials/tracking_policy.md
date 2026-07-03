---
title: Run a tracking policy
sidebar_position: 3
---

# Tutorial: Run a tracking policy

End-to-end: take a trained ONNX tracking policy, load it into the
**in-process** `humanoid_control::RLPolicyController` (this stack is the **System 0**
real-time layer), and watch the arms follow a LeRobot teleop dataset
under MuJoCo physics. By the end you'll know what the launch-time
`prepare` step produces, how the ONNX metadata schema makes everything
self-describing, and how to swap in your own policy without rewriting
any YAML.

## Time + materials

- 20 minutes
- A working workspace build
- One of: a local `.onnx` checkpoint, OR W&B credentials with access
  to a tracking run, OR access to the canonical Lite-tracking
  checkpoint (see [policy_runner reference](../reference/policy_runner.md)
  for the resolution path)
- Network access for the first run (pulls the LeRobot dataset from
  the HF Hub if you're using the W&B path)

## The mental model

There is no separate policy process. A launch-time `prepare` step turns
the checkpoint into artifacts, and the controller does inference itself,
inside the RT cycle:

```
   launch-time, once:
   ┌──────────────────────┐
   │ humanoid_control_policy prepare    │   (CLI, humanoid_control_policy — non-real-time)
   │   - resolve ONNX      │
   │     (local / W&B)     │
   │   - LeRobot motion    │
   │     → single-episode  │
   │     .mcap motion bag  │
   │   - emit overlay from  │
   │     ONNX metadata     │
   └──────────┬───────────┘
              │ rl_policy_params.yaml (+ .onnx + .mcap)
              ▼
   ┌──────────────────────┐
   │ RLPolicyController    │  (C++, humanoid_controllers — System 0, in-process)
   │   each RT tick:       │
   │   - pack observation  │
   │   - run ONNX inference│
   │   - read .mcap motion │
   │     reference         │
   │   - decode + scatter  │
   │     the action        │
   └──────────┬───────────┘
              │ 5 MIT command interfaces per joint
              ▼
   ┌──────────────────────┐
   │ MujocoSystem          │  (or RobstrideSystem)
   │   - apply τ = K·err   │
   │     + D·erṙ + ff      │
   └──────────────────────┘
```

The policy itself is **self-describing**: every constant it needs
(joint order, K_p, K_d, default pose, action scale, observation
terms, dataset id, tick rate) is baked into the ONNX's
`custom_metadata_map`. `prepare` transcodes that metadata into the
overlay, so the ONNX stays the single source of truth — you don't write
any of this into YAML.

## Step 1 — Bring up MuJoCo

The same launch as the previous tutorial, no gamepad needed:

```bash
ros2 launch humanoid_bringup_lite mujoco.launch.py
```

Wait for `zero_torque_controller` to come active.

## Step 2 — Walk to STANDBY

`rl_policy_controller` expects the arms in a sane starting pose.
Walk the FSM up to STANDBY. In a second terminal, drop into the env:

```bash
cd humanoid_control_ws
pixi shell
```

Then drive the FSM through `mode_manager`'s trigger services (the same
transitions the gamepad would fire):

```bash
# Gamepad equivalents, if you have one:
#   X    → DAMP
#   L1+A → LOAD_A (STANDBY, Pose A); wait ~4 s for is_finished:true
#   L1+B → LOAD_B (STANDBY, Pose B) — an alternate pose; either pose
#          can start either policy
#
ros2 service call /humanoid_control/mode/damp std_srvs/srv/Trigger
ros2 service call /humanoid_control/mode/load_a std_srvs/srv/Trigger

# Wait for is_finished:
ros2 topic echo /standby_controller_a/state
# ... is_finished: true
```

## Step 3 — Prepare and load the policy

In a third terminal:

```bash
# Option (a): local ONNX
ros2 launch humanoid_control_policy lite_policy.launch.py \
    checkpoint_file:=/path/to/policy.onnx

# Option (b): W&B run path (downloads + caches to ~/.cache/humanoid_control_policy/wandb/)
ros2 launch humanoid_control_policy lite_policy.launch.py \
    wandb_run_path:=IsaacLab-Training/mjlab/<run_id>

# Option (c): W&B run with a specific checkpoint pinned
ros2 launch humanoid_control_policy lite_policy.launch.py \
    wandb_run_path:=IsaacLab-Training/mjlab/<run_id> \
    wandb_checkpoint_name:=model_4000.onnx
```

The task family is selected by the ONNX `task_type` metadata — there is
no `task:=` argument. (`lite_tracking.launch.py` is kept as a thin
pass-through alias for the `launch-policy-tracking` pixi task.)

What happens behind the scenes:

1. The launch runs `humanoid_control_policy prepare` **synchronously** as a one-shot
   step (no long-lived Python node), which:
   - resolves the checkpoint to a local file via
     `checkpoint_loader.resolve_checkpoint` (downloading from W&B if
     needed, ~1 s once cached);
   - parses the ONNX `custom_metadata_map`. You'll see logs like:
     ```
     [prepare] checkpoint : /path/to/policy.onnx
     [prepare] task_type  : tracking
     [prepare] motion bag : ~/.cache/humanoid_control_policy/launch/motion_tracking_ep0 (240 frames, 2 bodies)
     [prepare] overlay    : ~/.cache/humanoid_control_policy/launch/rl_policy_params.yaml
     ```
   - pulls the LeRobot reference motion (parquet shards from HF Hub)
     keyed off `episode_index` and converts the chosen episode into a
     single-episode rosbag2 **`.mcap`** motion bag;
   - emits an `rl_policy_controller` parameter overlay
     (`rl_policy_params.yaml`) transcoded from the ONNX metadata,
     pointing the controller at both the `.onnx` and the `.mcap`.
2. The launch then loads `rl_policy_controller` into the running
   controller_manager **inactive**, with that overlay.

At this point the controller is loaded but not active, so nothing
changes physically. The in-process `RLPolicyController` does its own
ONNX inference and reads `/lite/joint_states` and `/imu/data` locally
once activated — there is no command topic to publish.

## Step 4 — STANDBY → START_LOCOMOTION

Wait for `is_finished: true` in `/standby_controller_a/state`, then
activate the policy through the FSM (in the FSM-walk terminal, inside
`pixi shell`):

```bash
ros2 service call /humanoid_control/mode/start_locomotion std_srvs/srv/Trigger
```

(Gamepad equivalent: **R1 + A**.) `mode_manager` switches the active
controller to `rl_policy_controller`. The motors immediately track the
policy — in MuJoCo you'll see the arms move through the tracking dataset.

Verify the controller is active:

```bash
ros2 topic echo --once /control_mode
# mode: 3   (LOCOMOTION)
# controller_name: rl_policy_controller
```

If the ONNX returns a non-finite action, `RLPolicyController` returns
`ERROR` and the controller_manager falls back to `damping_controller`
(see [Concepts → Safety pipeline](../concepts/safety_pipeline.md)).

## Step 5 — Inspect the data flow

The policy runs entirely in-process, so the observation inputs are the
two always-on streams the controller reads locally:

```bash
ros2 topic hz /lite/joint_states   # joint state broadcaster (RT update rate)
ros2 topic hz /imu/data            # IMU, if the observation uses it
ros2 topic echo --once /control_mode   # confirm LOCOMOTION / rl_policy_controller
```

There is no `MITCommand` stream to inspect: inference, motion replay,
and the command write all happen inside the RT `update()`.

## Step 6 — Shut down

DAMP first, then exit (still in the `pixi shell` terminal):

```bash
ros2 service call /humanoid_control/mode/damp std_srvs/srv/Trigger

# Then Ctrl+C the policy launch, then the bringup launch.
```

DAMP switches off `rl_policy_controller` and activates
`damping_controller`; the launch's `on_deactivate` cascades through the
controllers.

## What you came away with

| Skill | Page where it's documented in detail |
|---|---|
| Resolving an ONNX checkpoint (local / W&B) | [Reference → Policy runner](../reference/policy_runner.md) |
| The launch-time `prepare` step + ONNX metadata fields | same |
| LeRobot motion → `.mcap` bag conversion | same |
| The in-process `RLPolicyController` lifecycle | [Reference → Controllers](../reference/controllers.md) |
| The five-mode FSM + `START_LOCOMOTION` | [Concepts → Five-mode FSM](../concepts/five_mode_fsm.md) |

## Next

- [Concepts → Architecture](../concepts/architecture.md) — how the
  in-process System 0 policy tier and the launch-time `prepare` step fit
  the larger stack.
- [Concepts → Frozen schemas](../concepts/frozen_schemas.md) — what
  about this contract is frozen, and what's tunable.
