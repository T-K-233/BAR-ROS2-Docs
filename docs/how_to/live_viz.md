---
title: Live-visualize the robot
---

# Live-visualize the robot

Two interchangeable viewers ride on `/lite/joint_states` +
`/robot_description` and render the live kinematic chain. Pick
whichever fits your workflow; run two terminals if you want both at
once.

| | `rerun_viz` | `viser_viz` |
|---|---|---|
| Viewer | Native rerun window (auto-opens) | Browser at `http://<host>:8080` |
| Best for | Local desktop; timeline scrubbing; replay-style debugging | Headless robot machine; share over SSH tunnel; URL-shareable |
| URDF parser | `rerun.urdf.UrdfTree` (bundled with `rerun-sdk`) | `yourdfpy.URDF` |
| Dep source | `rerun-sdk` (pixi pypi) | `viser`, `yourdfpy`, `scipy` (pixi pypi) |

## Dependencies

Both viewers' dependencies ship in the pixi env — `pixi install`
already pulled them in. No extra `pip install` step is needed.

## Run from the host (tethered deployment default)

`viz.launch.py` is the host-side entrypoint of the two-machine
tethered split: it subscribes over DDS to the `/lite/joint_states`
stream `lite_real.launch.py` publishes from the onboard computer and
renders the live pose on the operator workstation.

Inside the workspace env (`cd humanoid_control_ws && pixi shell`):

```bash
# Default — viser, browser at http://localhost:8080
ros2 launch humanoid_bringup_lite viz.launch.py

# Native rerun window instead
ros2 launch humanoid_bringup_lite viz.launch.py viewer:=rerun

# Multi-robot or non-Lite — override the topic
ros2 launch humanoid_bringup_lite viz.launch.py joint_state_topic:=/<owner>/joint_states
```

`viewer:=` mirrors mjlab's `--viewer` flag so the same vocabulary
moves between training-time and deployment-time scripts. Pick `viser`
for headless / screen-recorded / shareable sessions; pick `rerun` for
local timeline scrubbing on a workstation with a display.

`lite_real.launch.py` itself does **not** spawn the viewers — visualisers
are host-side by deployment policy. See
[Architecture → deployment topology](../concepts/architecture.md)
for the rationale.

## Run standalone (any bringup, single-machine sim/dev)

For MuJoCo or any single-machine path, start the viewer node directly
instead of the launch wrapper. `ROS_DOMAIN_ID` matching is on you —
these talk to whatever's already on the local domain.

```bash
ros2 run humanoid_bringup_lite rerun_viz
ros2 run humanoid_bringup_lite viser_viz
```

Both work against any bringup that publishes `/robot_description`
(latched) and `/lite/joint_states` — silicon, MuJoCo, or
`mock_components`.

## Using `viser_viz` over SSH

`viser` serves the viewer on `0.0.0.0:8080` by default — so from any
machine with route to the robot:

```
http://<robot-ip>:8080
```

When you're remote, an SSH tunnel keeps the port off the LAN:

```bash
# On the laptop:
ssh -L 8080:localhost:8080 user@robot
# Now visit http://localhost:8080 in the laptop's browser.
```

The viewer is read-only — there's no command surface in either tool.
For drag-to-command interaction use `rqt_joint_trajectory_controller`
(stock) or `mit_slider_gui` (project).

## Performance notes

| Viewer | Typical CPU on a workstation |
|---|---|
| `rerun_viz` | ~5% per core for 14 joints @ 50 Hz; renders on GPU |
| `viser_viz` | ~10% per core; mostly websocket/JSON overhead |

Both subscribe `/robot_description` with TRANSIENT_LOCAL QoS and
parse the URDF once at startup; runtime cost is just the
per-`/lite/joint_states` callback + a tf update.

## Failure modes

| Symptom | Cause |
|---|---|
| Window opens but robot is blank / collapsed | Mesh `package://` URLs not resolving. Make sure `lite_description`'s install is on `AMENT_PREFIX_PATH` (pixi activation does this automatically once you `pixi shell` into `humanoid_control_ws/`). |
| `rerun_viz` says `ModuleNotFoundError: No module named 'rerun'` | The pixi env wasn't entered — run `cd humanoid_control_ws && pixi shell` first, then `ros2 run humanoid_bringup_lite rerun_viz`. |
| `viser_viz` complains about a missing `scipy` symbol | Stale env. Re-run `pixi install` to resync against `pixi.lock`. |
| Browser at `:8080` shows "this site can't be reached" | `viser_viz` not running — start it via `ros2 launch humanoid_bringup_lite viz.launch.py` (default viewer is `viser`), or wrong host in the URL. |
| Joints visible in `ros2 topic echo /lite/joint_states` but not moving in viewer | TF buffer staleness — restart the viewer; the URDF subscription may have been late to the latched message. |

## See also

- `rerun_viz` source: [`humanoid_bringup_lite/scripts/rerun_viz.py`](https://github.com/Berkeley-Humanoids/humanoid_control_ros2/blob/main/humanoid_bringup_lite/scripts/rerun_viz.py)
- `viser_viz` source: [`humanoid_bringup_lite/scripts/viser_viz.py`](https://github.com/Berkeley-Humanoids/humanoid_control_ros2/blob/main/humanoid_bringup_lite/scripts/viser_viz.py)
- `viz.launch.py` source: [`humanoid_bringup_lite/launch/viz.launch.py`](https://github.com/Berkeley-Humanoids/humanoid_control_ros2/blob/main/humanoid_bringup_lite/launch/viz.launch.py)
- [Reference → Launch args](../reference/launch_args.md) — the
  `viz.launch.py` arg table (`viewer`, `joint_state_topic`).
