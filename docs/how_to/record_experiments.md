---
title: Record experiments with rosbag (MCAP)
---

# Record experiments with rosbag (MCAP)

Capture a complete telemetry trace of any bringup — joints, controller
switches, safety status, policy I/O — to a [MCAP](https://mcap.dev)
file. MCAP is the cross-language replacement for the legacy `sqlite3`
rosbag backend; it's the default in ROS 2 Jazzy and what Foxglove
Studio / `mcap-cli` consume directly.

## Record everything

The one-liner most operators want:

```bash
ros2 bag record -s mcap --all -o lite_$(date +%Y%m%d_%H%M%S)
```

Breaking down the flags:

| Flag | Meaning |
|---|---|
| `-s mcap` | Use the MCAP storage plugin. Without this you get the legacy `sqlite3` `.db3` format. |
| `--all` | Subscribe every topic visible at start time. Late-joiners are *not* picked up automatically — restart the recorder if you launch new nodes. |
| `-o <dir>` | Output directory name. The recorder writes `<dir>/<dir>_0.mcap` plus a `metadata.yaml`. Stamping with `$(date …)` keeps successive runs from colliding. |

Stop with Ctrl+C. The MCAP file is finalized on shutdown.

## Record a focused subset

`--all` is heavy on disk and wall-clock CPU. For a tuning session
where you only care about the control loop, name the topics
explicitly:

```bash
ros2 bag record -s mcap -o tuning_$(date +%Y%m%d_%H%M%S) \
    /lite/joint_states \
    /standby_controller_a/state \
    /standby_controller_b/state \
    /safety_status \
    /joy \
    /tf /tf_static
```

There is no `/control_mode` topic to record anymore. "Which controller
is active" is a `/controller_manager/list_controllers` service query
(`ros2 control list_controllers`), not a recordable topic — capture the
per-controller state topics you care about (e.g.
`/standby_controller_a/state`) instead. `/joy` still records the raw
gamepad input that drove the switches.

For a System 1/2 ingress session (gravity-comp, VLA), also add the
command topic `/remote_policy_controller/command` (`humanoid_control_msgs/MITCommand`).
For piano runs, capture the live key state `/piano/key_state`
(`std_msgs/Float32MultiArray`, 0/1 per key) — the source for offline
F1 / precision / recall computed via `pianist_metrics` against the
policy's target keys.

## Tips

- **Where to put bags**: pick a path *outside* the workspace
  (`~/bags/...`) so `colcon build` doesn't try to index multi-GB
  `.mcap` files. The workspace's `.gitignore` already excludes
  `bag_*` / `*.mcap` at the repo root, but a path under `~` is
  safest.
- **TRANSIENT_LOCAL topics** (e.g. `/robot_description`,
  `/safety_status`): the recorder captures the latched value the
  moment it subscribes, so start `ros2 bag record` *after* the
  launch is up if you want the URDF in the bag.
- **Sim time**: when recording from MuJoCo the timestamps come from
  `/clock`, so the bag is already on sim time. Replay with
  `--clock` and start downstream consumers with `use_sim_time:=true`
  if you want consistent `now()` semantics across the playback.
- **Compression**: MCAP supports built-in zstd compression — add
  `--compression-mode message --compression-format zstd`. Roughly
  2× shrink on typical float-heavy `/lite/joint_states` traffic, at
  ~5% CPU overhead.

## Inspect a recording

```bash
# Topic list + message counts + duration
ros2 bag info -s mcap <bag-dir>

# Or use mcap-cli directly on the file (no ROS needed):
mcap info <bag-dir>/<bag-dir>_0.mcap
mcap list channels <bag-dir>/<bag-dir>_0.mcap
```

`mcap-cli` ships in the pixi env (available as `mcap …` inside
`pixi shell`). For interactive plotting, drop the `.mcap` into
[Foxglove Studio](https://foxglove.dev) (`foxglove-studio` package,
also pixi-installed).

## Replay

```bash
ros2 bag play -s mcap <bag-dir>
```

For replaying into a stack that uses sim time, add
`--clock 200` (publishes `/clock` at 200 Hz) and launch your
consumers with `use_sim_time:=true`. Note that replay does **not**
re-run the controllers — it just re-publishes the recorded topics.
To replay an action stream into the live controller chain, see
[Switch controllers manually](./switch_controllers_manually.md).

## Post-process piano runs

The `pianist_metrics` numpy package (installed via pixi pypi-deps from
the upstream `pianist-tracking-mj` repo) is the source of truth for
piano evaluation metrics. Capture the live key state during the run:

```bash
ros2 bag record -s mcap -o piano_$(date +%Y%m%d_%H%M%S) \
    /piano/key_state
```

The target keys are no longer published on a topic — they are a
reference term the in-process controller reads from the policy's
`.mcap` motion bag (produced by the launch-time `prepare` step). So the
offline target comes from that same motion bag, aligned to the recorded
`/piano/key_state`:

```python
import pianist_metrics as pm
# target  : (T, 88) bool from the policy's .mcap motion bag
# pressed : (T, 88) bool from /piano/key_state in the run bag
precision = pm.precision(target, pressed)
recall    = pm.recall(target, pressed)
f1        = pm.f1(target, pressed)
```

There is no live ROS node computing these — bag-based post-processing
is the deployment-side evaluation path.

## See also

- [Frozen schemas](../concepts/frozen_schemas.md) — why
  `/lite/joint_states` / `/safety_status` / etc. fields don't shift
  between releases (so old bags stay readable).
- [MCAP spec & tooling](https://mcap.dev/) — file format,
  `mcap-cli` reference, ecosystem.
