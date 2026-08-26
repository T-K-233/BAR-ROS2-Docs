---
title: Recover from a fault
---

# Recover from a fault

`/safety_status` reports a non-OK level. Nothing auto-DAMPs on it
anymore — `/safety_status` is **telemetry**, and reacting to it is the
operator's job. What to do depends on which flag tripped. This page is
the operator's runbook.

## How recovery works now

There are two independent mechanisms, and neither is the old
`mode_manager` auto-DAMP node (that node is gone):

- **Native controller fallback (automatic).** Each mode controller
  declares `fallback_controllers: [damping_controller]`. If a
  controller's `update()` returns ERROR, the controller_manager
  deactivates it and activates its fallback — `damping_controller`,
  which declares no fallback of its own. This happens at
  the controller_manager layer and is independent of `/safety_status`.
- **Operator reaction to `/safety_status` (manual).** A hardware bus
  fault is published on `/safety_status` as telemetry only — it does
  **not** switch modes for you. When you see a non-OK level, switch to
  STOP (gamepad `BACK`, which deactivates every mode) or DAMP (gamepad `X`
  → `damping_controller`), or use `ros2 control switch_controllers`.

## Read the status first

Open a shell into the workspace so `ros2` is on PATH:

```bash
cd humanoid_control_ws
pixi shell
ros2 topic echo /safety_status
# level: 2     # 0=OK, 1=WARNING, 2=FAULT, 3=CRITICAL
# flags: 8     # bitmask
# source: humanoid_devices_robstride/can0
# message: ""
```

Translate `flags`:

| Bit | Constant | Hex |
|---|---|---|
| 0 | `FLAG_BUS_OFF`           | `0x01` |
| 1 | `FLAG_RX_TIMEOUT`        | `0x02` |
| 2 | `FLAG_TX_QUEUE_OVERRUN`  | `0x04` |
| 3 | `FLAG_MOTOR_FAULT`       | `0x08` |
| 4 | `FLAG_TEMPERATURE_LIMIT` | `0x10` |
| 5 | `FLAG_INVALID_FRAME`     | `0x20` |

Multiple bits can be set simultaneously. The numeric value above
(`8` = `0x08`) means `MOTOR_FAULT` alone tripped.

## Per-flag recovery

### `FLAG_BUS_OFF` (sticky, level=CRITICAL)

**Cause**: kernel CAN socket open failed, or the kernel reported
`ENETDOWN` mid-operation.

**Recovery**:
1. Check the adapter: `ip -d link show <iface>`. If `BUS-OFF` or
   missing, unplug + replug the USB-to-CAN cable.
2. Bring the bus back up: `sudo ip link set <iface> up type can
   bitrate 1000000`.
3. Restart the launch — `BUS_OFF` is the one sticky flag in the
   plugin; it doesn't self-clear without a configure round-trip.

### `FLAG_RX_TIMEOUT` (level=FAULT)

**Cause**: one or more joints went silent for longer than
`rx_timeout_ms` (default 200 ms). Usually a motor that lost power,
a cable that came loose, or a bus the kernel briefly stopped reading
from.

**Recovery**:
1. Confirm motors are powered:
   `pixi run scan-bus --channel canN`
2. Confirm wiring — wiggle the daisy chain connector at each motor.
3. Restart the launch. `RX_TIMEOUT` clears on `on_activate` so a
   relaunch is sufficient; no power-cycle needed.

If one specific joint repeatedly times out, that motor or its
section of the bus has an issue. Substitute a known-good motor at
that ID and confirm.

### `FLAG_TX_QUEUE_OVERRUN` (level=WARNING)

**Cause**: kernel TX qdisc filling. Almost always motors-not-ACKing
or USB-adapter bottlenecking.

**Recovery**: see [Diagnose ENOBUFS](./diagnose_enobufs.md) for the
full runbook.

### `FLAG_MOTOR_FAULT` (level=FAULT)

**Cause**: a Robstride status / fault-report frame indicated a non-OK
internal motor state. The specific sub-cause is encoded in the motor
firmware's `fault_bits` byte, which the plugin folds into this
generic flag.

**Recovery**:
1. Reconfigure (relaunch). Some motor faults clear with a
   re-Enable. The plugin's `on_activate` issues a fresh Enable to
   every joint.
2. If the fault persists, single-step diagnosis:
   ```bash
   pixi run ping-bus --channel canN --id <X> --read-status
   ```
   The reply's `fault_bits` byte tells you which specific sub-cause:
   - `bit 0` = overtemperature (also raised as `FLAG_TEMPERATURE_LIMIT`)
   - `bit 1` = gate driver fault (usually means the motor went into
     overcurrent — under-spec actuator, mechanical jam)
   - `bit 2` = undervoltage (supply sag)
   - `bit 3` = overvoltage (regen during fast deceleration; can
     happen with a tiny PSU)
3. Vendor's MotorControlGUI may be needed if the motor latched and
   doesn't clear with a re-Enable.

### `FLAG_TEMPERATURE_LIMIT` (level=FAULT)

**Cause**: a motor exceeded its overtemp threshold. Surfaced
separately from `MOTOR_FAULT` because it's the most common motor
fault and has a specific operator response.

**Recovery**:
1. **Stop driving the joint immediately.** Let it cool for several
   minutes.
2. Reduce the operating point — lower `K_p`, lower `torque_limit`,
   or run less load on the joint.
3. If the motor reaches overtemp during STANDBY interpolation, the
   target pose may be reaching beyond what the actuator can hold
   against gravity — verify the URDF lower/upper limits are correct
   and the standby pose YAML doesn't put the joint past them.

### `FLAG_INVALID_FRAME` (level=WARNING)

**Cause**: a frame on the bus didn't match the Robstride protocol
(wrong comm-type code, wrong DLC). Single occurrences are usually
EMI glitches; recurring means another device is sharing the bus.

**Recovery**:
1. Single occurrence — ignore. The flag clears at the next tick if
   no further bad frames arrive.
2. Recurring — check for another device on the bus. CAN buses are
   shared; if another controller is connected the frames may
   collide. Disconnect the other device.

## After fixing — what to do

There is no auto-recovery: after a fault you are sitting wherever you
(or a controller fallback) last switched to — typically `zero_torque`
(STOP) or `damping` (DAMP). Even once `/safety_status` returns to OK,
nothing walks the robot back up for you.

```bash
# /safety_status is now OK (level=0), robot is in DAMPING or STOP.
# Bring it back up when you're satisfied it's steady.
# Via the gamepad:
#  L1+A   →   STANDBY (Pose A)
#  L1+B   →   STANDBY (Pose B)
#  L1+Y   →   STANDBY (Pose Y)
#  R1+A   →   LOCOMOTION
#  R1+B   →   REMOTE
# Or from the CLI:
ros2 control switch_controllers \
    --activate   standby_controller_a \
    --deactivate damping_controller
```

Switching is flat, so you can go straight to whichever mode you want
(see [Switch controllers manually](./switch_controllers_manually.md)).
Still, observe the robot in DAMPING/STOP for a few seconds first: a
fault that just cleared may re-occur, and you want to confirm it's
actually steady before commanding motion.

## Soft-restart in code

If you suspect transient flags are stuck:

```bash
# Force a switch through ZERO_TORQUE to reset accumulated state.
ros2 control switch_controllers \
    --deactivate damping_controller

# Then activate as usual:
ros2 control switch_controllers \
    --activate damping_controller
```

`on_activate` clears the accumulated `fault_flags_` (except sticky
`BUS_OFF`), so toggling through ZERO_TORQUE is the soft reset for
non-sticky flags.

## See also

- [Concepts → Safety pipeline](../concepts/safety_pipeline.md) — how the flags get set in the first place.
- [Reference → Messages](../reference/messages.md) — `SafetyStatus` field schema.
- [Diagnose ENOBUFS](./diagnose_enobufs.md) — for `FLAG_TX_QUEUE_OVERRUN` specifically.
