# Launch args

Every Humanoid Control bringup follows the same vocabulary. Each robot ships **two
parallel launches** — `lite_real.launch.py` for silicon, `lite_mujoco.launch.py` for
MuJoCo physics. Operators pick the *launch file* rather than flipping a
`use_mock_hardware` flag on a single one. The xacro still accepts
`use_mock_hardware:=true` for direct ad-hoc visualization, but no
bundled launch enables that path.

Launches live in two repos:

- `Humanoid Control` ships the Lite + Prime control-plane bringups (`humanoid_bringup_lite`,
  `humanoid_bringup_prime`), the URDF inspector (`humanoid_bringup_lite`),
  and the policy prepare-and-load launches (`humanoid_control_policy`).
- `pianist_ros2` ships piano-task-specific launches: scene composition
  (`pianist_bringup`), the piano prepare-and-load launch, and the USB-MIDI
  driver (both `pianist_policy`).

## `humanoid_bringup_lite/launch/lite_view.launch.py`

URDF inspector — no controller_manager, no physics.

| Arg | Default | Effect |
|---|---|---|

Implicit: forces `use_mock_hardware:=true` on the xacro so the
`<ros2_control>` block is harmless when `robot_state_publisher` parses
the URDF.

## `humanoid_bringup_lite/launch/lite_real.launch.py`

Real-hardware Lite bringup. Loads **two** `humanoid_devices_robstride/RobstrideSystem`
instances, one per physical SocketCAN bus (`LiteLeftArm` claims CAN ids
11..17 on the left bus, `LiteRightArm` claims 21..27 on the right bus).

| Arg | Default | Effect |
|---|---|---|
| `hardware_config`     | `<humanoid_bringup_lite share>/config/lite_hardware.yaml` | Per-machine bus + joint config. Maps the two `<ros2_control>` blocks to specific SocketCAN ifnames and joint IDs. Override to retarget a robot whose CAN ifnames differ. |
| `calibration_file`    | `<humanoid_bringup_lite share>/config/calibration.yaml` | Absolute path to the per-physical-robot zero-offset YAML. Pass `''` for identity calibration (only the URDF `direction` sign flip applies, no offset). See [Hardware specs → Bus-bring-up checklist](./hardware_specs.md#bus-bring-up-checklist) for how to regenerate. |
| `enable_joy_teleop` | `true` | `true` spawns the `joy_teleop` node that maps gamepad buttons directly to `/controller_manager/switch_controller`. `false` skips it — used by `calibrate.launch.py` and raw-debug bringups where the operator drives controllers directly via `ros2 control switch_controllers`. |
| `enable_gamepad`      | `true`  | `true` spawns `joy_node` so `joy_teleop` can read `/joy`. **The launch hard-fails on missing `joy_dev`.** Pass `false` on a keyboardless lab box and switch controllers directly with `ros2 control switch_controllers` instead. |
| `joy_dev`             | `/dev/input/js0` | Path passed verbatim to `joy_node`'s `dev` parameter. Override when the onboard computer enumerates the gamepad as something other than `js0` (multiple gamepads plugged in, udev rename). The pre-launch check fails fast when the specific path is missing and lists any other `/dev/input/js*` devices it can see, so the error message tells you which override to pass. Ignored when `enable_gamepad:=false`. |

The active-policy target is picked by the gamepad button, not a launch
arg (convention: A = local policy, B = remote): R1+A activates
`rl_policy_controller` (the in-process learned policy —
tracking / piano / locomotion), R1+B activates
`remote_policy_controller` (the System 1/2 external-command ingress —
gravity-comp today, VLA later; see [Controllers](./controllers.md)).

**Visualisers are not in this launch.** `lite_real.launch.py` is the
onboard-computer entrypoint of the tethered deployment split — it
publishes `/robot_description` and `/lite/joint_states` over DDS but
spawns no viewers. Run `ros2 launch humanoid_bringup_lite viz.launch.py`
on the operator workstation (see the
[`viz.launch.py` section](#humanoid_bringup_litelaunchvizlaunchpy) below).

Implicit on the xacro: `use_mock_hardware:=false sim_mujoco:=false`.

## `humanoid_bringup_lite/launch/viz.launch.py`

Host-side live visualiser. Runs on the **operator workstation** of the
tethered deployment split (not on the onboard computer). Subscribes to
the `/robot_description` (latched) and joint-state topic that
`lite_real.launch.py` is publishing on the onboard side and renders the
live pose locally — purely a DDS consumer, no hardware coupling.

| Arg | Default | Effect |
|---|---|---|
| `viewer` | `viser` | `viser` (browser at `http://localhost:8080`, works headless, screen-records cleanly) or `rerun` (native window, better for time-cursor / multi-stream UX on a workstation with a display). Mirrors mjlab's `--viewer` flag. `choices=` rejects other values at parse time. |
| `joint_state_topic` | `/lite/joint_states` | Topic the viewer subscribes to. Override for a multi-robot deployment or a non-Lite robot. |

Only one viewer spawns per launch — pick at invocation. Run the
launch twice in two terminals if you need both viewers
simultaneously (same pattern as running two mjlab `play` processes
upstream).

## `humanoid_bringup_lite/launch/calibrate.launch.py`

Bundles `lite_real.launch.py` with three overrides
(`calibration_file:='' enable_joy_teleop:='false' enable_gamepad:='false'`)
and adds the `calibrate_robot` observer node. The plugin runs with identity
calibration so `/lite/joint_states` carries `direction × raw_motor_pos`,
which is the frame the homing-offset formula expects.

| Arg | Default | Effect |
|---|---|---|
| `hardware_config` | `<bundled lite_hardware.yaml>` | Forwarded to `lite_real.launch.py`. |
| `output` | `$PWD/calibration.yaml` | Path the calibration observer writes on Ctrl+C. After verifying, `mv` it over `humanoid_bringup_lite/config/calibration.yaml` to make it the default for the next `lite_real.launch.py`. |

The observer reads per-joint static config (`direction`, `lower_limit`,
`upper_limit`, `can_id`) from `/robot_description` — there's no parallel
YAML config for it to drift against. The YAML schema keeps the same
per-joint keys as
[`T-K-233/Lite-Lowlevel-Python`](https://github.com/T-K-233/Lite-Lowlevel-Python)'s
JSON output, so values move between the two stacks unchanged.

## `humanoid_bringup_lite/launch/lite_mujoco.launch.py`

MuJoCo Lite bringup. Loads `mujoco_ros2_control/MujocoSystem` inside the
`mujoco_sim` process (which hosts the controller_manager as a physics
plugin).

| Arg | Default | Effect |
|---|---|---|
| `hardware_config` | `<bundled lite_hardware.yaml>` | Same as the real bringup; the bus mapping is unused in MuJoCo but the joint list is read. |
| `scene` | `lite_dummy` | MJCF scene basename under `lite_description/robots/lite_dummy/mjcf/`. Default `lite_dummy` (robot only). Task packages from sibling repos (e.g. `pianist_ros2`'s `pianist_bringup`) compose their own runtime scene XML and override this arg with their composed-file basename. |
| `enable_gamepad` | `true` | Same hard-fail-on-missing-`/dev/input/js*` behaviour as the real bringup. |

Implicit:

- The xacro is invoked with `sim_mujoco:=true`. **`sim_mujoco` wins over
  `use_mock_hardware`** in the xacro's `<plugin>` selector — see the
  decision tree in [Packages](packages.md#lite_description--prime_description-external).
- Every node runs with `use_sim_time:=true`. Time advances at MuJoCo's
  pace via `/clock`.
- `humanoid_bringup_lite/config/sim_overrides.yaml` is layered on top of
  `humanoid_controllers/config/humanoid_control_lite_controllers.yaml` so the real-hardware
  launch stays sim-time-free.

## `humanoid_bringup_prime/launch/prime_real.launch.py`

Stub real-hardware Prime bringup. Designed to load both
`ethercat_driver/EthercatDriver` (eRob arms) and `humanoid_devices_sito/SitoSystem`
(auxiliary) — two concurrent `<ros2_control>` blocks in the URDF.

The Prime URDF / MJCF is **not yet imported** from CAD —
`humanoid_bringup_prime` is a stub today and this launch will not wire
controllers until that import lands.

## `humanoid_bringup_prime/launch/prime_mujoco.launch.py`

Stub mirror of `humanoid_bringup_lite/lite_mujoco.launch.py` for Prime, pending
the Prime MJCF import.

## `humanoid_control_policy/launch/lite_policy.launch.py`

Prepares and loads the in-process tracking-family policy. It runs
`humanoid_control_policy prepare` **synchronously** (resolve the ONNX, convert the
LeRobot motion to a `.mcap` bag, emit the `rl_policy_controller`
overlay), then spawns `rl_policy_controller` *inactive* with that
overlay into the running controller_manager. The operator's R1+A button
(via `joy_teleop`) activates it.
There is no separate runner process; the task is selected by the ONNX
`task_type` metadata.

| Arg | Default | Effect |
|---|---|---|
| `checkpoint_file` | (empty) | Absolute path to a local ONNX checkpoint. Mutually exclusive with `wandb_run_path`. |
| `wandb_run_path` | (empty) | W&B run path (`entity/project/run_id`); `prepare` downloads + caches the ONNX under `~/.cache/humanoid_control_policy/wandb/<run_id>/`. |
| `wandb_checkpoint_name` | (empty) | Specific checkpoint filename inside the run (default: newest `model_*`). |
| `motion_file` | (empty) | Local LeRobot dataset directory; overrides `registry_name` and the ONNX `dataset_repo_id`. |
| `registry_name` | (empty) | HuggingFace LeRobot repo id override. |
| `episode_index` | `0` | LeRobot dataset episode index to convert. |
| `out_dir` | `~/.cache/humanoid_control_policy/launch` | Where the prepared `.onnx` copy, `.mcap` bag, and `rl_policy_params.yaml` overlay are written (fixed so the spawner can find the overlay). |

Each arg is forwarded verbatim to the `prepare` CLI (`--checkpoint-file`,
`--wandb-run-path`, …). Sibling tracking-task families (piano, etc.) live
in their own repos and register their own launch (see
`pianist_policy/piano_policy.launch.py` below).

## `humanoid_control_policy/launch/lite_tracking.launch.py` (alias)

Thin pass-through wrapper around `lite_policy.launch.py`, kept for
existing scripts that reference it by name.

## `pianist_policy/launch/piano_policy.launch.py`

Piano counterpart of `lite_policy.launch.py`: runs `pianist_policy
prepare` (resolve the ONNX, convert the song to a key-state `.mcap`,
emit the piano overlay), then spawns the same in-process
`rl_policy_controller` *inactive*. The piano task is selected by the
ONNX `task_type='piano'` metadata — there is no `task:` arg. The live
key state is published separately by `piano_state_bridge` (sim) /
`midi_keyboard_driver` (hardware) as `std_msgs/Float32MultiArray` on
`/piano/key_state`.

Same args as `lite_policy.launch.py`, plus:

| Arg | Default | Effect |
|---|---|---|
| `skip_stride` | `1` | Stride between lookahead frames (the training-time value). |
| `key_state_topic` | `/piano/key_state` | Live key-state topic (`Float32MultiArray`) the controller subscribes to for the `key_pressed` extern term. |

## `pianist_policy/launch/midi_keyboard_driver.launch.py`

Starts the real-piano USB-MIDI driver standalone. Opens a MIDI input
port and publishes `std_msgs/Float32MultiArray` (0.0/1.0 per key) on
`/piano/key_state` — the same topic + type + QoS as the sim-side
`piano_state_bridge`, so the in-process controller cannot tell them
apart.

| Arg | Default | Effect |
|---|---|---|
| `port_name` | `''` (auto-detect first available) | MIDI input port name (or substring match). Use `python -c 'import mido; print(mido.get_input_names())'` to list available ports. |
| `output_topic` | `/piano/key_state` | Topic to publish on. |
| `publish_rate_hz` | `50.0` | Publish rate for the latest pressed-state. |

## `pianist_bringup/launch/mujoco.launch.py`

MuJoCo bringup for the piano task. Composes the Lite robot and the
piano MJCF into one scene file (`_runtime_lite_piano.xml`) inside
`lite_description`'s `robots/lite_dummy/mjcf/` share dir, then delegates to
`humanoid_bringup_lite/lite_mujoco.launch.py` with `scene:=_runtime_lite_piano`.
Also spawns the `piano_state_bridge` sim-side bridge so
`/piano/key_state` exists on the sim path.

| Arg | Default | Effect |
|---|---|---|
| `enable_gamepad` | `true` | Forwarded to `humanoid_bringup_lite/lite_mujoco.launch.py`. |
| `robot_type` | `arms` | `arms`, `biped` or `biped_debug`. Selects the bring-up launch and the lite_description variant. |
| `hardware_config` | `<humanoid_bringup_lite share>/config/lite_hardware.yaml` | Forwarded. |

`scene:=` is **not** exposed — `pianist_bringup` controls that internally.

## xacro args (`lite_description/robots/lite_dummy/xacro/lite_dummy.urdf.xacro`)

The launch args ultimately feed these xacro args. Useful when driving
xacro directly (e.g. in a sim2sim eval harness):

| Arg | Default | Effect |
|---|---|---|
| `use_mock_hardware` | `true` | Select `mock_components/GenericSystem` — single combined `<ros2_control>` block. |
| `sim_mujoco` | `false` | **Wins over `use_mock_hardware`** — select `mujoco_ros2_control/MujocoSystem`, also single combined block. |
| `hardware_config` | (empty) | YAML the xacro reads to learn the per-machine bus + joint mapping. The launches set this; ad-hoc xacro calls usually leave it empty. |
| `calibration_file`    | `""`   | Passed verbatim as a `<param name="calibration_file">` on both real-hardware blocks. Empty = identity calibration. |

## Common combinations

The launches are grouped by where they run. See
[Concepts → Architecture → Deployment topology](../concepts/architecture.md#deployment-topology)
for the rationale behind the split.

**Single-machine dev path** (sim, calibration, URDF inspection — no
robot involved, no tether):

```sh
# Drag joints in RViz, no controllers.
ros2 launch humanoid_bringup_lite lite_view.launch.py

# MuJoCo physics, /clock from sim time.
ros2 launch humanoid_bringup_lite lite_mujoco.launch.py

# Lite + piano in MuJoCo (pianist_bringup composes the scene).
ros2 launch pianist_bringup mujoco.launch.py

# Calibrate the zero pose (writes ./calibration.yaml on Ctrl+C).
ros2 launch humanoid_bringup_lite calibrate.launch.py
```

**Robot onboard computer** (CM + hardware + joy_teleop + gamepad — boots
the real control plane, no visualisers, no policy runner):

```sh
# Real Lite, gamepad on by default. Press R1+B to activate the remote policy.
ros2 launch humanoid_bringup_lite lite_real.launch.py

# Same, but on a keyboardless lab box (switch controllers via ros2 control switch_controllers).
ros2 launch humanoid_bringup_lite lite_real.launch.py enable_gamepad:=false

# Gamepad enumerated as js1 instead of js0 (multiple controllers plugged in).
ros2 launch humanoid_bringup_lite lite_real.launch.py joy_dev:=/dev/input/js1
```

**Robot onboard computer — prepare + load a policy** (the in-process
inference now runs on the robot, so the prepare-time ML deps and the
artifacts live here; the launches load `rl_policy_controller` into the
local controller_manager):

```sh
# Prepare + load the tracking policy (humanoid_control_policy) from a W&B run.
ros2 launch humanoid_control_policy lite_policy.launch.py \
    wandb_run_path:=user/proj/run_id \
    wandb_checkpoint_name:=model_2000.onnx

# Prepare + load a piano policy (pianist_policy) against a song.
ros2 launch pianist_policy piano_policy.launch.py \
    wandb_run_path:=user/proj/run_id

# USB-MIDI keyboard driver (publishes /piano/key_state locally —
# loopback to the in-process controller; does not cross the tether).
ros2 launch pianist_policy midi_keyboard_driver.launch.py
```

**Operator workstation** (host side of the tether — visualisers; talks
to the robot strictly via DDS over a wired link):

```sh
# Live URDF + /lite/joint_states viewer (browser at :8080 by default).
ros2 launch humanoid_bringup_lite viz.launch.py                  # viser
ros2 launch humanoid_bringup_lite viz.launch.py viewer:=rerun    # native rerun window
```

Both machines must share `ROS_DOMAIN_ID` and (recommended) `RMW_IMPLEMENTATION`.
