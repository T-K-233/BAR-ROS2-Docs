---
id: use_pixi_tasks
title: Workspace commands (pixi tasks)
sidebar_label: Workspace commands (pixi tasks)
---

# Workspace commands (pixi tasks)

The rest of this site documents commands in canonical `ros2 launch …` /
`ros2 run …` form. Those work everywhere — Jetson, workstation, CI.

On top of that, every Humanoid Control workspace exposes the same
standardized command interface, organized in **two levels**:

| Level | Commands | What it is |
|---|---|---|
| **1 — lifecycle tasks** | `setup` `build` `test` `clean` `doctor` | pixi tasks with reserved names *and* meanings — identical in every workspace |
| **2 — workspace tasks** | `sim` `real` `policy` `deploy-sim` `deploy-real` `viz` `calibrate` + utility tasks (`ping-bus`, `scan-bus`, …) | pixi tasks with reserved names — each workspace declares the ones that apply to its stack |

Discovery is built in: bare `pixi run` (or `pixi task list`) prints the
workspace's task menu with descriptions. This page explains each level
and how to extend them.

:::note[What happened to the `hc` CLI]
Rev 1 of this interface had a third level: a packaged `hc` CLI (the
`humanoid_control_cli` package) carrying diagnostics, viewers, and
calibration verbs. Rev 2 retired it — the package is deleted, and its
verbs became workspace tasks (`hc bus ping` → `pixi run ping-bus`,
`hc viz` → `pixi run viz`, …) or plain documented `ros2 run` commands.
The full mapping is in
[Reference → Diagnostics and utility commands](../reference/cli_tools.md).
:::

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
particular, **no scenario or utility task ever triggers a build** (a
hardware bringup must never start with a surprise rebuild). If the
workspace isn't built, those tasks fail with guidance pointing at
`pixi run build`; `doctor` is the staleness check.

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

## Level 2 — workspace tasks

Reserved names; each workspace declares the ones that apply, scoped to
its stack. Two vocabularies live here: **scenario tasks** and
**utility tasks**.

### Scenario tasks

Grammar: `scenario[-qualifier]`, **at most one qualifier**, where the
unqualified name is the workspace's default target. The qualifier
encodes only the *primary* task variant; every secondary parameter
(robot, backend, checkpoint, scene, …) stays a ROS launch argument:

```sh
pixi run sim-piano robot:=prime policy:=latest    # right
pixi run sim-prime-piano-latest                   # wrong — name explosion
```

The scenario words have **uniform semantics in every workspace**:

- `sim` / `real` — **plant bringup only**: hardware or physics plus the
  controller stack, **no policy**.
- `policy` — prepare and load a policy against an already-running
  plant.
- `deploy-sim` / `deploy-real` — the **one-command pipeline**: bringup
  *plus* policy in a single invocation.
- `viz` — live state viewer of a running robot.
- `calibrate` — calibration bringup.

In `humanoid_control_ws` (scope = the base control stack; unqualified =
Lite):

| Task | Wraps |
|---|---|
| `pixi run sim` | `ros2 launch humanoid_bringup_lite lite_mujoco.launch.py` |
| `pixi run real` | `ros2 launch humanoid_bringup_lite lite_real.launch.py` |
| `pixi run sim-prime` / `real-prime` | the `humanoid_bringup_prime` equivalents |
| `pixi run sim-piano` | `ros2 launch pianist_bringup mujoco.launch.py` |
| `pixi run policy` | `ros2 launch humanoid_control_policy lite_policy.launch.py` |
| `pixi run policy-piano` | `ros2 launch pianist_policy piano_policy.launch.py` |
| `pixi run deploy-sim` | `ros2 launch humanoid_bringup_lite deploy.launch.py backend:=mujoco` |
| `pixi run deploy-real` | `ros2 launch humanoid_bringup_lite deploy.launch.py backend:=real` |
| `pixi run viz` | `ros2 launch humanoid_bringup_lite viz.launch.py` (`viewer:=viser` default, `viewer:=rerun`) |
| `pixi run calibrate` | `ros2 launch humanoid_bringup_lite calibrate.launch.py` |

The `deploy-*` tasks take the policy source as launch args
(`wandb_run_path:=` or `checkpoint_file:=`); `deploy-real` additionally
accepts `hardware_config:=` / `calibration_file:=` for the per-machine
setup. The task `description` always states the scope; `pixi task list`
shows it.

In a deployment workspace (e.g.
[Lite-Deployment](https://github.com/Berkeley-Humanoids/Lite-Deployment)),
`deploy-sim` / `deploy-real` are the same one-command pipeline —
bringup plus policy — because that is the workspace's reason to exist.
The scenario words never change meaning per workspace; a deployment
repo that doesn't declare plant-only `sim` / `policy` tasks simply
documents the canonical `ros2 launch` forms instead.

### Utility tasks

Frequently-used diagnostics get free kebab-case task names. Each one
**must be a one-line wrapper** over its canonical `ros2 run` /
`ros2 launch` command — no logic, no flags of its own:

| Task | Wraps |
|---|---|
| `pixi run ping-bus` | `ros2 run humanoid_devices_robstride robstride_ping` |
| `pixi run scan-bus` | `ros2 run humanoid_devices_robstride robstride_discover` |
| `pixi run profile-bus` | `ros2 run humanoid_devices_robstride robstride_probe` |

Rarely-used tools deliberately get **no task** — their canonical
`ros2 run` / `ros2 launch` forms are documented instead (e.g.
`robstride_probe_report`, `mit_slider_gui`, the standalone
`viser_viz` / `rerun_viz` executables, `lite_view.launch.py`). See
[Reference → Diagnostics and utility commands](../reference/cli_tools.md).

## Forwarding arguments

Tasks are thin, argument-less wrappers, so trailing arguments forward
verbatim, the same way they do under the raw command:

```sh
pixi run real enable_gamepad:=false
pixi run real hardware_config:=$HOME/lite_hardware.jetson.yaml
pixi run deploy-sim wandb_run_path:=entity/project/run-id
pixi run policy checkpoint_file:=$HOME/model.onnx
pixi run ping-bus --iface can0 --id 11
pixi run scan-bus --iface can1 --scan-to 32
```

## Escape hatches

The tasks are shortcuts, not a wall. Two first-class ways out:

- `pixi shell` — drop into the sourced environment and type plain
  `ros2 launch …` / `ros2 run …` exactly as the launch-file docs show.
- `pixi run -- ros2 run humanoid_devices_robstride mit_slider_gui` —
  run *any* command inside the pixi-managed env from a vanilla
  terminal, no task declaration needed.

## The reference block

The `viz`, `calibrate`, and bus-utility one-liners are meant to be
**identical in every workspace** that carries the Lite stack. This TOML
block is the copy source — paste it into a consumer workspace's
`pixi.toml` verbatim rather than re-typing the wrappers, so
`pixi run ping-bus` means exactly the same thing everywhere:

```toml
# --- Humanoid Control task reference block -------------------------------
# Copy verbatim. Each task is a one-line wrapper over the canonical
# command; trailing arguments forward verbatim.

[tasks.viz]
cmd = "ros2 launch humanoid_bringup_lite viz.launch.py"
description = "Live state viewer of a running robot (viewer:=viser default, viewer:=rerun)"

[tasks.calibrate]
cmd = "ros2 launch humanoid_bringup_lite calibrate.launch.py"
description = "Calibration bringup — writes calibration.yaml on Ctrl+C"

[tasks.ping-bus]
cmd = "ros2 run humanoid_devices_robstride robstride_ping"
description = "Single-actuator GetDeviceId ping, read-only (--iface, --id)"

[tasks.scan-bus]
cmd = "ros2 run humanoid_devices_robstride robstride_discover"
description = "Scan a CAN bus for Robstride device ids, read-only (--iface, --scan-to)"

[tasks.profile-bus]
cmd = "ros2 run humanoid_devices_robstride robstride_probe"
description = "Link RTT / jitter probe against one actuator (--iface, --id)"
```

## Task lists per workspace

`humanoid_control_ws` declares 25 tasks:

- **Lifecycle (+ local extras)**: `setup` `build` `build-all` `test`
  `test-result` `lint` `check` `clean` `doctor` `gen-dds` `test-dds`
- **Scenario**: `sim` `real` `sim-prime` `real-prime` `sim-piano`
  `policy` `policy-piano` `deploy-sim` `deploy-real` `viz` `calibrate`
- **Utility**: `ping-bus` `scan-bus` `profile-bus`

[Lite-Deployment](https://github.com/Berkeley-Humanoids/Lite-Deployment)
declares: `setup` `build` `clean` `doctor` `deploy-sim` `deploy-real`
`teleop`. (Its former `sim` / `real` tasks — which were the full
bringup-plus-policy pipeline — are renamed `deploy-sim` /
`deploy-real` under rev 2, freeing `sim` / `real` for their uniform
plant-only meaning.)

## Adding a new command

Decision rule, in order:

1. **A scenario** (bringup, policy, deploy, viz, calibrate) — use the
   reserved vocabulary, plus at most one `-qualifier` for the primary
   variant; secondary parameters stay launch args.
2. **A frequently-used diagnostic or utility** — a free kebab-case
   task that is a one-line wrapper over the canonical `ros2` command.
   If it already exists in the reference block above, copy it from
   there instead of re-typing it.
3. **Operates on the workspace** (fetch, build, verify) — lifecycle
   task, universal names only.
4. **Needs root or mutates host state** (CAN buses, kernel) — a script
   under `scripts/`, run explicitly with `sudo`, never a task.
5. **Rarely used** — no task at all; document the canonical
   `ros2 …` command.

Give every task a `description` — `pixi task list` is the menu:

```toml
[tasks.my-scenario]
cmd = "ros2 launch my_pkg my_launch.py"
description = "One line explaining scope and key launch args"
```

## Tradeoffs vs. plain `ros2 launch`

When to use the tasks:

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
