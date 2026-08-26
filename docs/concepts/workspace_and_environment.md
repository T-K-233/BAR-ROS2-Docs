# Workspace & environment

This page explains *how the repository and the environment are
organized*, and **why**. The mechanical setup steps live in
[Installation](../getting_started/installation.md); the `pixi run …`
alias surface lives in
[Workspace shortcuts with pixi](../how_to/use_pixi_tasks.md). Read this
one when you want to understand the model those steps assume — where new
code should go, what gets committed where, and how a fresh machine
reproduces the workspace exactly.

## The three-tier code model

A robotics project mixes code with very different needs: hard-real-time
controllers, one-off data tools, and heavy ML pipelines. Forcing all of
it into one environment and one repository creates dependency conflicts
(CUDA versions, PyTorch wheels vs. the ROS conda packages), build-system
mismatches (colcon vs. uv), and release-cadence mismatches.

`Humanoid Control` separates code by **what it needs to talk to**, not by language
or topic:

| | **Tier 1 — ROS native** | **Tier 2 — workspace tooling** | **Tier 3 — separate project** |
|---|---|---|---|
| Location | `src/<pkg>/` | per-package `scripts/`, the workspace pixi tasks, a future top-level `scripts/` | its own git repo, outside the workspace |
| Examples | `humanoid_controllers`, `humanoid_devices_robstride`, `humanoid_drivers_socketcan` | `robstride_probe`, calibration helpers, `pixi run ping-bus` | `Lite-SDK2`, `Lite-Gravity-Compensation` |
| Build / run | `colcon` + `ros2 run` | `pixi run …` | own toolchain (`uv run …`) |
| Imports `rclpy`? | **yes** | no | **no** |
| Talks to ROS via | native pub / sub / service / action | doesn't talk to running nodes | **DDS (CycloneDDS)** + file handoff |
| Built by colcon? | yes | no (`COLCON_IGNORE`) | n/a — outside the workspace |

### Tier 3 is the interesting boundary

A Tier-3 process has **zero ROS package dependencies**. It is a plain
Python program — free to pull in PyTorch, ONNX Runtime with a specific
CUDA build, JAX, whatever — that joins the same DDS bus the Tier-1 nodes
already use. This is the same pattern the Unitree SDK2 Python ecosystem
follows: a process with no ROS deps participating in the robot's DDS
network.

The catch with "just speak DDS directly" is usually that you have to
hand-mirror the message types, and they drift. `Humanoid Control` avoids that by
**generating** them:

- [`humanoid_control_msgs_dds`](../reference/packages.md) generates wire-compatible
  `cyclonedds` types from `humanoid_control_msgs/msg/*.msg` (`pixi run gen-dds`),
  including the RMW type-name mangling and `rt/` topic conventions. A CI
  drift test + a CDR wire round-trip test keep it honest.
- [`lite_sdk2`](../how_to/talk_to_humanoid_control_from_python.md) layers a
  publisher/subscriber API (topic + QoS registry) on top of those types.
- [`Lite-Gravity-Compensation`](../tutorials/run_gravity_compensation.md)
  is the reference Tier-3 project: it depends on `lite_sdk2`, computes
  gravity torques in MuJoCo, and publishes `humanoid_control_msgs/MITCommand` onto
  `/remote_policy_controller/command` (consumed by the
  `RemotePolicyController`) over raw CycloneDDS — no `rclpy`, no colcon
  sourcing.

Edit a `.msg`, re-run `gen-dds`, and every Tier-3 consumer stays in sync
with the ROS schema.

### When to promote a tier

- **Tier 2 → a new `humanoid_control_*` package** when a script grows into a real ROS
  node (it needs to publish/subscribe, claim interfaces, or run inside the
  controller_manager process).
- **Tier 2 → Tier 3** when it (a) needs dependencies that conflict with
  ROS at the *system* level (CUDA versions, specific PyTorch/JAX wheels),
  (b) develops its own contributors / release cadence / test suite, or
  (c) is consumed by multiple workspaces. The system-level conflict is the
  decisive one — pixi can resolve most Python-level conflicts in-workspace
  (see below); a CUDA/driver/wheel conflict means a clean separate
  environment is genuinely simpler.

## Why pixi + RoboStack

The environment — ROS 2 Jazzy, the compiler toolchain, every Python and
native dependency — is managed by [pixi](https://pixi.sh) against the
[RoboStack](https://robostack.github.io) conda channel, pinned by
`humanoid_control_ws/pixi.toml` + `pixi.lock`.

- **Reproducible.** `pixi.lock` pins exact versions and hashes; the same
  lockfile resolves the same environment on every developer machine and on
  the Jetson (`linux-64` + `linux-aarch64`).
- **No sudo, no system pollution.** Everything lives under `humanoid_control_ws/.pixi/`.
  No host Ubuntu-version dependency, no system-wide `ros-jazzy-desktop`.
- **One tool for conda *and* PyPI.** pixi drives `uv` internally for the
  PyPI side (`onnxruntime`, `huggingface-hub`, the visualisers), so there
  is no separate `pip install` step and no second lockfile.

Two consequences worth internalizing:

- **No rosdep, no apt.** rosdep would call `conda install`, which a pixi
  environment doesn't support. `<exec_depend>` entries in `package.xml`
  are *informational* (kept for ROS-packaging correctness); the real
  install path is `pixi.toml`. If a build needs a dep it doesn't have, the
  colcon build fails with a clear error — add the dep to `pixi.toml` and
  rerun.
- **Pick one ROS at a time.** RoboStack and an apt `ros-jazzy` install
  resolve the same library names against different toolchains. Never
  `source /opt/ros/jazzy/setup.bash` inside a `pixi shell`.

:::note[Tier-2 isolation, if you ever need it]
If a Tier-2 script's dependency genuinely conflicts with the ROS env,
you don't reach for a second tool — you add a pixi *feature* + environment
and run `pixi run -e tools …`. One manifest, one lockfile. A separate uv
project under `scripts/` would just duplicate what pixi already does.
:::

:::tip[The dev environment is not the robot environment]
This is a *development* environment optimized for velocity and
reproducibility, deliberately matched to the deployment target only at the
ROS-distro level (Jazzy everywhere). Test against the real on-robot setup
before deployment; see [Architecture → deployment topology](./architecture.md).
:::

## Version control: a config repo + a first-party monorepo

The repository layout is a deliberate split:

- **`humanoid_control_ws` is a thin, config-only git repo.** It tracks only the
  environment and tooling — `pixi.toml`, `pixi.lock`, `.gitattributes`
  (which marks `pixi.lock` as generated), `canup.sh`, and the task
  definitions — and **gitignores all of `src/`** (keeping a `.gitkeep`).
- **First-party code lives in the `Humanoid Control` monorepo.** All the `humanoid_control_*`
  packages are co-developed and released together, so they share one repo
  (its own git history) checked out under `src/humanoid_control/`, rather than the
  strict `ros2/ros2` one-repo-per-package convention. The piano task is
  the sibling `pianist_ros2` repo under `src/pianist_ros2/`.
- **Third-party dependencies are pinned, not vendored.**
  `src/humanoid_control/humanoid_control.repos` lists `ethercat_driver_ros2` and the three
  `mujoco_*` packages; `vcs import` (`pixi run setup`) pulls them into
  `src/`. Pin to commit SHAs for releases.

This keeps the *environment* history (`humanoid_control_ws` / `pixi.lock`) on a separate
track from the *code* history (`Humanoid Control`), while still letting `Humanoid Control`
be tagged and reused on its own.

### The reproducibility chain

Three independent pins compose into a deterministic rebuild:

```sh
git clone <humanoid_control_ws-repo> && cd humanoid_control_ws
git clone …/humanoid_control.git src/humanoid_control   # + pianist_ros2 for the piano task
pixi install        # exact env from pixi.lock
pixi run setup      # vcs import third-party deps into src/
pixi run build      # colcon build
```

`pixi.lock` pins the environment; the `Humanoid Control` / `pianist_ros2`
checkouts pin the first-party tree; `humanoid_control.repos` pins the third-party tree.
Together they reproduce the workspace bit-for-bit.

## See also

- [Installation](../getting_started/installation.md) — the step-by-step
  setup.
- [Workspace shortcuts with pixi](../how_to/use_pixi_tasks.md) — what each
  `pixi run …` alias does.
- [Talk to Humanoid Control from Python](../how_to/talk_to_humanoid_control_from_python.md)
  — building a Tier-3 client over DDS.
- [Packages reference](../reference/packages.md) — what each package ships.
