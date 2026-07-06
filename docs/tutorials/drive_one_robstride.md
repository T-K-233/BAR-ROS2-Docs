---
title: Drive one Robstride end-to-end
sidebar_position: 1
---

# Tutorial: Drive one Robstride end-to-end

Get a single bench-top Robstride motor moving under our plugin.
You'll wire one actuator to one CAN bus, bring up a minimal
`ros2_control` stack, and command position via the slider GUI.

By the end you'll have hands-on familiarity with:
- The Robstride wire protocol (via `robstride_ping`).
- The `humanoid_devices_robstride/RobstrideSystem` lifecycle.
- The 5-interface MIT command surface.
- How calibration plays into the command-to-encoder transform.

This is the simplest "everything wired up" lesson — one motor, one
bus, no FSM, no production realism. If you only have a CAN-USB
adapter and no robot, you can get most of the way through this
tutorial with vcan loopback (covered at the bottom).

## Time + materials

- 30 minutes
- One Robstride actuator (rs-00, rs-02, or rs-05 — anything we support)
- One USB-to-CAN adapter (CANable, PCAN-USB, Kvaser — anything `gs_usb` /
  `socketcan` likes)
- One CAN cable with the right connector for your motor
- A 24 V bench PSU for the motor

## Step 1 — Wire the bench

```
+24V PSU ─── motor power input
GND      ─── motor ground
CAN_H    ─── adapter CAN_H
CAN_L    ─── adapter CAN_L
```

Terminate at 120 Ω if the cable is long; for a 30 cm bench setup
you'll get away without termination on most adapters.

Power on the motor *before* opening the CAN socket — frames need
acks, and a powered-down motor doesn't ack.

## Step 2 — Bring the bus up

```bash
sudo ip link set can0 up type can bitrate 1000000
ip -d link show can0
# Look for: state UP, can state ERROR-ACTIVE
```

## Step 3 — Ping the motor

```bash
cd humanoid_control_ws
pixi run ping-bus --iface can0 --id <X>
# TX  GetDeviceId  id=...
# RX  GetDeviceId reply  device=<X>  uid=...
# stats: rx=1 tx=1 rx_dropped=0 tx_failed=0
```

(`ping-bus` is the workspace task wrapping
`ros2 run humanoid_devices_robstride robstride_ping`; trailing args
forward verbatim.) Replace `<X>` with the motor's configured ID
(factory default 0x7F on new Robstride; vendor tool to reassign). If
you don't know the ID, scan:

```bash
pixi run scan-bus --iface can0 --scan-to 127
```

A clean reply confirms three things: the bus is up, the motor is
powered, and the protocol byte order is correct. You haven't
Enabled the motor yet — `GetDeviceId` is read-only.

## Step 4 — Read live status (still read-only)

```bash
pixi run ping-bus --iface can0 --id <X> --read-status
# RX  OperationStatus  device=<X>  pos= ... rad  vel= 0.0  torque= 0.0  temp= ... C  fault_bits=0x00
```

`--read-status` briefly Enables, prompts an `OperationStatus` reply,
then Disables. The `pos` value is the raw encoder reading — no
calibration applied. With the motor unconstrained on the bench you
should see a stable value; if you rotate the shaft by hand and
re-ping, `pos` should change correspondingly.

## Step 5 — Launch the single-motor test stack

`humanoid_devices_robstride` ships a self-contained launch for this
(enter the workspace env first — `pixi shell` — so `ros2` is on PATH):

```bash
cd humanoid_control_ws
pixi shell
ros2 launch humanoid_devices_robstride single_robstride_gui.launch.py \
    can_id:=<X>
```

This brings up:
- A 1-joint URDF describing your motor (`single_robstride_test`).
- `ros2_control_node` loading `humanoid_devices_robstride/RobstrideSystem`.
- `joint_state_broadcaster` (active).
- `zero_torque_controller` (active — safe).
- `forward_mit_controller` (loaded **inactive**).

Verify in a second terminal:

```bash
cd humanoid_control_ws
pixi shell
ros2 topic echo --once /joint_states
# name: ['actuator_1']
# position: [<some real value, not exactly 0.0>]

ros2 control list_controllers
# zero_torque_controller       active
# forward_mit_controller       inactive
```

## Step 6 — Slider GUI

The slider GUI is a rarely-used tool, so it has no pixi task — run
the canonical executable (from any terminal, `pixi run --` provides
the env):

```bash
pixi run -- ros2 run humanoid_devices_robstride mit_slider_gui
```

A Qt window with five sliders (position, velocity, effort, kp, kd)
plus a live readout of the measured `(pos, vel, eff)`.

**Don't activate the forward controller yet.** While
`zero_torque_controller` is active, the sliders are publishing into
the void.

## Step 7 — Move it

In a third terminal (inside `pixi shell`):

```bash
ros2 control switch_controllers \
    --deactivate zero_torque_controller \
    --activate   forward_mit_controller
```

The motor is now under the slider GUI. Workflow:

1. Click **Snap to measured** in the GUI. The position slider
   matches the current encoder reading.
2. Drag **kp** up gradually: 0 → 2 → 5. Try to back-drive the motor;
   it should resist with increasing strength.
3. Drag the **position slider** by ±0.1 rad. The motor should
   follow.
4. Drag **kd** to 0.5–1.0 if you see oscillation.
5. Set **effort** to ±0.5 Nm to feel the feedforward path — the
   motor leans into that torque even with kp=kd=0.

You're now driving an actuator end-to-end via our plugin. The same
five fields go to the firmware verbatim on real hardware; the same
fields go to `qfrc_applied` on MuJoCo.

## Step 8 — Shutdown

Back to safe, then close:

```bash
ros2 control switch_controllers \
    --deactivate forward_mit_controller \
    --activate   zero_torque_controller

# Then Ctrl+C the launch terminal.
```

The plugin's `on_deactivate` sends Disable to the motor; the bus
goes silent.

## (Optional) vcan loopback for when you don't have hardware

If you only have a CAN-USB adapter without a motor handy, or you're
on a CI runner with neither, you can run *most* of this tutorial
against a virtual CAN interface:

```bash
sudo modprobe vcan
sudo ip link add dev vcan0 type vcan
sudo ip link set up vcan0
```

Then run the same `pixi run ping-bus --iface vcan0` and
`pixi run scan-bus --iface vcan0`. You won't get replies
(nothing's listening), but the TX path lights up and you can see
your own frames with `candump vcan0`. The single-motor launch will
boot but report `RX_TIMEOUT` in `/safety_status`.

## What you came away with

| Skill | Page where you'll use it again |
|---|---|
| `robstride_ping` / `robstride_discover` | [Probe CAN bus](../how_to/probe_can_bus.md) |
| `mit_slider_gui` | [mit_slider_gui how-to](../how_to/mit_slider_gui.md) |
| Manual `switch_controllers` | [Switch without FSM](../how_to/switch_controllers_manually.md) |
| The 5 MIT interfaces | [MIT command surface](../concepts/mit_command_surface.md) |

Next tutorial: [MuJoCo + full FSM walkthrough](./mujoco_fsm_walk.md).
