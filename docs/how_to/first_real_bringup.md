# First real-hardware bringup

Recipe for getting the physical Lite from "powered off in the corner"
to "`/lite/joint_states` flowing, motors compliant under `zero_torque`".
Once those signals are green you've reached parity with the
[Lite 101](../getting_started/lite_101.md) MuJoCo lesson — every
subsequent how-to (calibrate, drive a joint, switch to STANDBY) builds
on this baseline.

![Lite real-hardware bringup sequence](/img/diagrams/how_to__first_real_bringup__01.svg)

This is **read-only on the silicon** — no `STANDBY` motion happens
here. That's deliberate; verify everything compliant before commanding
any pose.

## Prerequisites

- Workspace built (`colcon build --symlink-install` from `humanoid_control_ws/`,
  inside `pixi shell`).
- USB-to-CAN adapters plugged into the workstation. Both arms' buses
  are visible at `can0` and `can1` (typical) or whatever the host
  assigned — `ip -br link show type can` to confirm.
- A pre-existing `humanoid_bringup_lite/config/calibration.yaml` for this
  physical robot. The bundled file works for the development robot;
  if you're on a different unit, [calibrate first](./calibrate_zero_pose.md).
- Robot **power is on** at the wall, but motors can be in any pose.

## Step 1 — Bring the CAN buses up

CAN interfaces drop to "DOWN" on a reboot. Bring both up at the
Robstride bitrate:

```bash
sudo ip link set can0 down 2>/dev/null
sudo ip link set can0 up type can bitrate 1000000
sudo ip link set can1 down 2>/dev/null
sudo ip link set can1 up type can bitrate 1000000

ip -d link show can0   # expect "UP" and "ERROR-ACTIVE"
ip -d link show can1   # same
```

If either interface refuses to come up, the adapter may be hung —
unplug and replug the USB cable, then retry. (`ERROR-PASSIVE` is also
acceptable; `BUS-OFF` means power-cycle the adapter.)

## Step 2 — Confirm motors are alive

A read-only scan before anything claims the bus (`scan-bus` is the
workspace task wrapping
`ros2 run humanoid_devices_robstride robstride_discover`):

```bash
cd humanoid_control_ws
pixi run scan-bus --iface can0 --scan-to 32
# Expect 7 actuators at ids 11..17

pixi run scan-bus --iface can1 --scan-to 32
# Expect 7 actuators at ids 21..27
```

`robstride_discover` only sends `GetDeviceId`; no `Enable`, no MIT
frames. Safe to run with whatever stack is up. **If you see ENOBUFS
warnings**, the actuators aren't powered — see
[Diagnose ENOBUFS](./diagnose_enobufs.md).

## Step 3 — Launch the bringup

```bash
pixi shell    # enter the workspace env so ros2 is on PATH
ros2 launch humanoid_bringup_lite lite_real.launch.py
```

Default args: `hardware_config:=<bundled lite_hardware.yaml>
calibration_file:=<bundled> enable_joy_teleop:=true
enable_gamepad:=true joy_dev:=/dev/input/js0`. The `hardware_config`
YAML provides the per-machine bus + joint mapping (left arm on `can0`
with ids 11..17, right arm on `can1` with ids 21..27 on the
development robot). The default `enable_gamepad:=true` hard-fails if
the resolved `joy_dev` path is missing; the error message lists any
other `/dev/input/js*` devices it can see so you can override with
`joy_dev:=/dev/input/jsN`. Pass `enable_gamepad:=false` (or
`enable_joy_teleop:=false`) on a keyboardless lab box and switch
controllers with `ros2 control switch_controllers` directly instead
(see [Switch controllers manually](./switch_controllers_manually.md)).

`lite_real.launch.py` boots the **onboard-computer side** of the tethered
deployment split: hardware plugins, the control-mode controllers, the
`joy_teleop` button mapper, and the gamepad driver. Visualisers
(`ros2 launch humanoid_bringup_lite viz.launch.py`)
and policy runners (`ros2 launch humanoid_control_policy lite_policy.launch.py …`)
live on the operator workstation — matching `ROS_DOMAIN_ID` is enough
for them to see each other. See
[Concepts → Architecture → Deployment topology](../concepts/architecture.md#deployment-topology).

Watch the launch logs for:

```
[ros2_control_node-1] Loaded hardware 'LiteLeftArm'  from plugin 'humanoid_devices_robstride/RobstrideSystem'
[ros2_control_node-1] Loaded hardware 'LiteRightArm' from plugin 'humanoid_devices_robstride/RobstrideSystem'

[ros2_control_node-1] SocketCanBus opened on 'can0'
[ros2_control_node-1] SocketCanBus opened on 'can1'
[ros2_control_node-1] Loaded calibration_file '...' (7/7 joints matched).
[ros2_control_node-1] Loaded calibration_file '...' (7/7 joints matched).
[ros2_control_node-1] Successful 'activate' of hardware 'LiteLeftArm'
[ros2_control_node-1] Successful 'activate' of hardware 'LiteRightArm'
[spawner-N] Configured and activated zero_torque_controller
```

Both bus components activated, both calibration files matched 7/7
joints, `zero_torque_controller` is active. The motors should now be
holding zero torque — fully back-drivable by hand.

## Step 4 — Verify in a second terminal

```bash
cd humanoid_control_ws
pixi shell

# 14 joints reporting at the configured update rate
ros2 control list_controllers
# Expect: joint_state_broadcaster (active), zero_torque_controller (active),
#         damping_controller / standby_controller_a / standby_controller_b / remote_policy_controller (inactive)

ros2 topic hz /lite/joint_states
# average rate: 50.0 (± 0.2)

ros2 topic echo --once /lite/joint_states | head -5
# header / 14 names / real-looking positions (NOT all 0.0 — that'd mean motors un-Enabled)

ros2 topic echo --once /safety_status
# level: 0    flags: 0    source: humanoid_devices_robstride/can0  (then a second one for can1)
```

The "all 0.0 positions" signal is the most useful early-warning: it
means motors aren't sending status frames back, almost always because
the Enable frame was dropped. Power cycle the actuators and relaunch.

## Step 5 — Sanity-check the calibration

Hand-rotate one arm a few degrees. The values in `ros2 topic echo
/lite/joint_states` should change in the expected direction and by a
plausible magnitude (radians, not encoder ticks).

If a joint reports positions far outside the URDF limits when you
move it through its range, the `direction` or `homing_offset` is
wrong for that joint — see [Calibrate the zero pose](./calibrate_zero_pose.md).

## Step 6 — Shut down

End in a known-safe state:

```bash
# In the launch terminal:
Ctrl+C
```

The `joy_teleop` node (if enabled) and every controller's
`on_deactivate` run, then `RobstrideSystem::on_deactivate` sends
`Disable` to every motor. The bus goes quiet within a tick;
`candump can0` will confirm.

## Common boot-time failures

| Log line | Likely cause | Fix |
|---|---|---|
| `Failed to open SocketCAN interface 'canN'` | Bus wasn't up at launch time | Step 1, then relaunch |
| `Interface 'canN' is not up (flags=...)` | Same as above, caught by our SIOCGIFFLAGS guard | Same |
| `Loaded calibration_file '...' (0/7 joints matched)` | YAML keys don't match URDF joint names | Inspect the file; common cause is editing it after a URDF rename |
| `CAN write() returned -1 (errno=No buffer space available)` | Actuator power off (no ACKs → qdisc fills) | Power the motors |
| `Failed to configure controller 'rl_policy_controller'` | Placeholder `observation_dim=0` in YAML | Already dropped from the inactive-spawner batch; if it reappears, drop it again |

Wider diagnostics live in [Troubleshooting](../reference/troubleshooting.md).

## What you can do next

- [Calibrate the zero pose](./calibrate_zero_pose.md) if positions
  look offset.
- [Switch controllers manually](./switch_controllers_manually.md) to
  exercise DAMPING / STANDBY without the gamepad.
- [MuJoCo mode walkthrough](../tutorials/mujoco_fsm_walk.md) to
  walk the same control-mode flow in simulation.
