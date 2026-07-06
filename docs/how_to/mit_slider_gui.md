---
title: Drive a single joint with mit_slider_gui
---

# Drive a single joint with `mit_slider_gui`

A Qt slider window that publishes the five MIT command fields
(`position`, `velocity`, `effort`, `stiffness`, `damping`) to a
running `forward_command_controller/MultiInterfaceForwardCommandController`.
Useful for:

- Sanity-checking a freshly calibrated joint by manually commanding a
  target and watching it track.
- Quick gain tuning before committing values to YAML.
- One-off motion captures for sysid.

The visual style matches `rqt_reconfigure` because it uses the same
`python_qt_binding` shim under the hood.

:::warning[This will move motors]
The slider GUI is a manual command path. Plan the test before
activating the forward controller. Start with gains at zero, snap the
position slider to "measured position" before raising stiffness, and
keep the workspace clear.
:::

## Prerequisites

- Workspace built.
- A working real-hardware bringup ([First real-hardware bringup](./first_real_bringup.md)).
- A `forward_command_controller/MultiInterfaceForwardCommandController`
  loaded in the controllers YAML, claiming all 5 MIT interfaces on
  the target joint. The single-actuator test config in
  `humanoid_devices/humanoid_devices_robstride/test/single_robstride_gui_controllers.yaml`
  is the canonical example.

## Step 1 — Launch the test stack

For a single-motor sanity check there's a dedicated launch (inside
the workspace env — `cd humanoid_control_ws && pixi shell`):

```bash
ros2 launch humanoid_devices_robstride single_robstride_gui.launch.py
```

The launch composes a `controller_manager` and starts the
`mit_slider_gui` executable; if you want the slider GUI alone against
an already-running controller manager, run `ros2 run humanoid_devices_robstride
mit_slider_gui` directly.

This brings up:
- `controller_manager` against the single Robstride test URDF
- `joint_state_broadcaster` (active)
- `zero_torque_controller` (active — safe default)
- `forward_mit_controller` (loaded, **inactive**)

In a second terminal, open the slider GUI. It's a rarely-used tool,
so it has no pixi task — run the canonical executable (plain
`ros2 run …` inside a `pixi shell`, or via `pixi run --` from any
terminal):

```bash
pixi run -- ros2 run humanoid_devices_robstride mit_slider_gui
```

A Qt window appears with five sliders (position, velocity, effort,
kp, kd) and a live readout of the measured `(pos, vel, eff)`.

## Step 2 — Activate the forward controller (only when ready)

The motors are still under `zero_torque` at this point — fully
compliant. To start commanding (from inside `pixi shell`):

```bash
ros2 control switch_controllers \
    --deactivate zero_torque_controller \
    --activate   forward_mit_controller
```

The motors **immediately** apply whatever the sliders currently say.
This is why you set sensible defaults first — see Step 3.

## Step 3 — Slider workflow

The safe order:

1. **Click "Snap to measured"**. The position slider jumps to the
   current encoder reading. This means raising stiffness next won't
   yank the joint to a wrong target.
2. **Raise `kp` gradually** (say 2 → 5 → 10) and feel the resistance.
   Try to back-drive the joint; you should feel it pull back.
3. **Slowly drag the position slider** to command motion. Magnitude
   ~0.1 rad first to confirm direction; widen once direction is right.
4. **Raise `kd`** (typically 0.5 → 1.0) if the joint oscillates around
   the target.
5. **Set `effort`** to a small value (e.g. 0.5 Nm) if you want to
   verify the feedforward path; the joint will lean against gravity
   in addition to the PD term.

## Step 4 — Shut down

Always end in `zero_torque`:

```bash
# Drop kp / kd / effort to 0 with the sliders, OR:
ros2 control switch_controllers \
    --deactivate forward_mit_controller \
    --activate   zero_torque_controller
```

Then `Ctrl+C` the launch. The plugin's `on_deactivate` sends Disable
to the motor.

## Driving a single joint of the full Lite

The default config tests one joint. To drive a single arm joint of
the full Lite without disturbing the others, the cleanest path is:

1. Launch the normal Lite bringup with `enable_mode_manager:=false`.
2. Load a forward command controller separately (inside `pixi shell`):

```bash
ros2 control load_controller \
    --set-state inactive \
    --param-file <YAML with forward_command_controller config> \
    forward_one_joint
```

3. Switch the target joint's command claim from `zero_torque_controller`
   to `forward_one_joint` — but the FSM controllers claim *all* the
   joints, so this requires deactivating `zero_torque_controller`
   on the full robot. In practice it's easier to load a
   `forward_command_controller` that claims the target joint AND
   the un-targeted joints with stiffness=0 / damping=0 / effort=0.

For most workflows the dedicated single-actuator launch is the right
tool. Move to the full Lite only when you want multi-joint
interactions.

## Limitations

- The slider rates publish at the GUI's tick (~30 Hz). The plugin's
  `update()` runs at 50 Hz, so commands have ~33 ms granularity. Fine
  for tuning, not for high-bandwidth tracking.
- `MultiInterfaceForwardCommandController` writes commands one to one,
  no rate limiting or smoothing. A big slider jump becomes a step
  command.
- Closing the GUI window while the forward controller is active
  leaves the last-written values in the cmd buffers. Always switch
  back to `zero_torque_controller` before closing.

## See also

- The GUI source: [`humanoid_devices_robstride/scripts/mit_slider_gui.py`](https://github.com/Berkeley-Humanoids/humanoid_control/blob/main/humanoid_devices/humanoid_devices_robstride/scripts/mit_slider_gui.py).
- [Concepts → MIT command surface](../concepts/mit_command_surface.md) — what each slider does.
- [Switch controllers without the FSM](./switch_controllers_manually.md).
