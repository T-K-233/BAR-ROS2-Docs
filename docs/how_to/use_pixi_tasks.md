---
id: use_pixi_tasks
title: Workspace commands (pixi tasks + hc)
sidebar_label: Workspace commands (pixi + hc)
---

# Workspace commands (pixi tasks + hc)

The rest of this site documents commands in canonical `ros2 launch …` /
`ros2 run …` form. Those work everywhere — Jetson, workstation, CI.

On top of that, every Humanoid Control workspace exposes the same
standardized command interface, organized in **three levels**:

| Level | Commands | What it is |
|---|---|---|
| **1 — lifecycle tasks** | `setup` `build` `test` `clean` `doctor` | pixi tasks with reserved names *and* meanings — identical in every workspace |
| **2 — product toolbox** | `hc bus` / `hc motor` / `hc viz` / `hc calibrate` | a packaged CLI on `PATH` — ships with the code, identical everywhere the stack is installed |
| **3 — scenario tasks** | `sim` `real` `policy` (+ variants) | pixi tasks with reserved *names* — each workspace defines their scope |

Discovery is built in: bare `pixi run` (or `pixi task list`) prints the
workspace's task menu with descriptions, and bare `hc` prints the
toolbox menu. This page explains each level and how to extend them.

:::tip[Why this layer exists]
`pixi run build` is shorter than the colcon invocation it wraps, but the
bigger win is that **every task runs inside the pixi-managed
environment** — ROS 2 Jazzy, the colcon overlay, the visualiser PyPI
deps, and the right `RCUTILS_CONSOLE_OUTPUT_FORMAT` are sourced
automatically. Calling `pixi run …` from a vanilla terminal works
without an explicit `pixi shell` first.
:::

## Day one: one command

```sh
pixi run build     # installs the locked env, imports sources, builds
pixi run doctor    # verifies the result; prints what to fix if unhealthy
```

`pixi run` self-heals the environment (like `uv run`), and `build`
chains the `setup` task, which is idempotent and **cached**: it only
re-executes when `humanoid_control.repos` changes or after a `clean`, so
daily builds never touch the network. Nothing else auto-chains — in
particular, **no scenario task ever triggers a build** (a hardware
bringup must never start with a surprise rebuild; `doctor` is the
staleness check).

## Level 1 — lifecycle tasks

Reserved names with identical semantics in every workspace
(`humanoid_control_ws`, the `*-Deployment` repos):

| Task | Meaning |
|---|---|
| `pixi run setup` | fetch/prepare sources beyond pixi itself (`vcs import --skip-existing`); idempotent, cached |
| `pixi run build` | build the workspace's default lane (chains `setup`) |
| `pixi run test` | run the workspace's tests (linters excluded — see `lint`) |
| `pixi run clean` | wipe `build/ install/ log/`; never touches `src/` or `.pixi/` |
| `pixi run doctor` | health check: root, env, `/opt/ros` contamination, sources, overlay |

Workspaces add local extras at the same level — in `humanoid_control_ws`:
`build-all` (include the EtherCAT/Prime lane), `test-result`, `lint`
(the version-stable ament linters), `check` (`test` + `lint`, the local
pre-push gate), `gen-dds`, `test-dds`. Colcon *style* flags
(`--symlink-install`, compile-commands) live in
`config/colcon-defaults.yaml` via `COLCON_DEFAULTS_FILE`, so a manual
`colcon build` inside `pixi shell` behaves identically to
`pixi run build`.

## Level 2 — the `hc` toolbox

Diagnostics, viewers, and calibration ship **with the code** as the
`hc` CLI (`humanoid_control_cli`), not as per-workspace tasks — it is on
`PATH` in any environment that has the stack, whether built from source
or installed from the `berkeley-humanoids` binary channel:

| Command | What it does |
|---|---|
| `hc bus ping` | single-actuator GetDeviceId ping (no Enable) |
| `hc bus discover` | scan a CAN bus for Robstride device ids |
| `hc bus probe` / `hc bus probe-report` | link RTT/jitter probe + report |
| `hc motor slider` | live MIT-mode slider GUI against one motor |
| `hc viz` | live state viewer of a running robot (`viewer:=viser` default, `viewer:=rerun`) |
| `hc viz urdf` | static URDF/kinematic inspector — sliders + RViz, no robot needed |
| `hc calibrate` | calibration bringup (writes `calibration.yaml`) |

Every verb `execvp`s into the canonical `ros2 run` / `ros2 launch`
command, so signals and trailing arguments pass straight through
(`hc bus ping --iface can0 --id 11`). Run `hc help` for the menu.

The scope rule: `hc` carries only commands whose **meaning is invariant
across workspaces**. Anything whose scope depends on the workspace
(`sim`, `real`, `policy`) is a task, level 3.

## Level 3 — scenario tasks

Reserved *names*; each workspace defines their scope. Grammar:
`scenario[-qualifier]`, **at most one qualifier**, where the
unqualified name is the workspace's default target. The qualifier
encodes only the *primary* task variant; every secondary parameter
(robot, backend, checkpoint, scene, …) stays a ROS launch argument:

```sh
pixi run sim-piano robot:=prime policy:=latest    # right
pixi run sim-prime-piano-latest                   # wrong — name explosion
```

In `humanoid_control_ws` (scope = the base control stack; unqualified =
Lite):

| Task | Wraps |
|---|---|
| `pixi run sim` | `ros2 launch humanoid_bringup_lite mujoco.launch.py` |
| `pixi run real` | `ros2 launch humanoid_bringup_lite real.launch.py` |
| `pixi run sim-prime` / `real-prime` | the `humanoid_bringup_prime` equivalents |
| `pixi run sim-piano` | `ros2 launch pianist_bringup mujoco.launch.py` |
| `pixi run policy` | `ros2 launch humanoid_control_policy lite_policy.launch.py` |
| `pixi run policy-piano` | `ros2 launch pianist_policy piano_policy.launch.py` |

In a deployment workspace (e.g.
[Lite-Deployment](https://github.com/Berkeley-Humanoids/Lite-Deployment)),
`sim` / `real` mean **the full task stack** — bringup plus policy in one
command — because that is the workspace's reason to exist. The task
`description` always states the scope; `pixi task list` shows it.

## Forwarding arguments

Scenario tasks are thin, argument-less wrappers, so trailing launch
arguments forward verbatim, the same way they do under raw
`ros2 launch`:

```sh
pixi run real enable_gamepad:=false
pixi run real hardware_config:=$HOME/lite_hardware.jetson.yaml
pixi run policy checkpoint_file:=$HOME/model.onnx
pixi run policy-piano wandb_run_path:=entity/project/run-id
```

## Adding a new command

Decision rule, in order:

1. **Invariant meaning everywhere** (a diagnostic, viewer, calibration
   tool) — add an `hc` verb in `humanoid_control_cli`, never a task.
2. **Scenario or workspace-local script** — add a task in that
   workspace's `pixi.toml`, using the reserved scenario vocabulary
   where it applies (`sim`, `real`, `policy`, plus at most one
   `-qualifier` for the primary variant; secondary parameters stay
   launch args), free kebab-case otherwise. Give it a `description` —
   `pixi task list` is the menu.
3. **Operates on the workspace** (fetch, build, verify) — lifecycle
   task, universal names only.
4. **Needs root or mutates host state** (CAN buses, kernel) — a script
   under `scripts/`, run explicitly with `sudo`, never a task.
5. **Rarely used** — no alias at all; document the canonical
   `ros2 …` command.

```toml
[tasks.my-scenario]
cmd = "ros2 launch my_pkg my_launch.py"
description = "One line explaining scope and key launch args"
```

## Tradeoffs vs. plain `ros2 launch`

When to use the tasks and `hc`:

- One-off interactive bringups where you'll type the command often.
- Operator runbooks — `pixi run real` reads more cleanly than the full
  launch path.
- CI scripts that need the pixi-managed env (a task inherits it
  automatically, no `pixi shell` wrapping needed).

When to reach for plain `ros2 launch …`:

- Inside a sourced `pixi shell` — the canonical form is what launch-file
  docstrings and this site document.
- When porting commands into another shell, an SSH cheatsheet, or a
  service unit on a machine that doesn't have pixi installed.
- When the surface you're documenting is the launch file itself (the
  task is a workspace-level shortcut, not a launch feature).
