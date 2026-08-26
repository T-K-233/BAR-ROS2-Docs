---
title: Probe actuators on a CAN bus
---

# Probe actuators on a CAN bus

Quick recipes for inspecting what's on a CAN bus *without* loading
the controller_manager. Use these before a real-hardware bringup to
verify wiring and DIP-switch IDs, or as the first step in any
"motors aren't responding" debug.

All of these are **read-only**: no Enable, no MIT operation control,
no parameter writes. Safe against a powered robot in any state.

## Confirm the kernel sees the bus

```bash
ip -br link show type can
# Expected:
#   can0     UP    <NOARP,UP,LOWER_UP,ECHO>
#   can1     UP    <NOARP,UP,LOWER_UP,ECHO>
```

`UP` is what you want. `DOWN` means run [the bring-up commands](../reference/quick_reference.md#can-bus-setup).
`UNKNOWN` (no state column) means the kernel sees the adapter but no
`ip link set` has configured a bitrate yet.

Detail per interface:

```bash
ip -d link show can0
# Look for: state UP, can state ERROR-ACTIVE, bitrate 1000000
```

`ERROR-ACTIVE` is the healthy state — frames are flowing both ways
and the bus is acking. `ERROR-WARNING` is transient and self-recovers;
`ERROR-PASSIVE` means many errors lately (often actuator power off);
`BUS-OFF` is hard-stop and requires a power-cycle of the adapter.

## Scan all IDs on a bus

`scan-bus` is the workspace task wrapping
`ros2 run humanoid_devices_robstride robstride_discover`; trailing
args forward verbatim:

```bash
cd humanoid_control_ws
pixi run scan-bus --channel can0
pixi run scan-bus --channel can1
```

Default scan range: 1..32. Sends one `GetDeviceId` per ID with 8 ms
spacing, then collects replies for 200 ms after the last ping. Output:

```
=== Scan results on can0 ===
  scanned : 1..32 (32 ids)
  found   : 7 actuator(s)
    id=11  (0x0B)  uid=3A58300194613802
    id=12  (0x0C)  uid=578F3002A042320E
    ...
```

The `uid` is the motor's MCU UID, useful for distinguishing two
otherwise-identical motors that have the same firmware ID.

For Lite the expected set is 11..17 on `can0` (left arm) and 21..27
on `can1` (right arm).

### Wider scan ranges

```bash
# Default range is 1..32; widen if you suspect IDs outside that.
pixi run scan-bus --channel can0 \
    --scan-from 1 --scan-to 127

# Tighter scan (faster) if you only want to check specific IDs:
pixi run scan-bus --channel can0 \
    --scan-from 11 --scan-to 17
```

### Slowing the scan

If the bus is slow / cheap-USB-adapter, raise `--per-id-wait-ms`:

```bash
pixi run scan-bus --channel can0 \
    --per-id-wait-ms 20
```

## Single-motor probe

When you know the ID and want a deeper status check:

```bash
pixi run ping-bus --channel can0 --id 11
# TX  GetDeviceId  id=...
# RX  GetDeviceId reply  device=11  uid=...
# stats: rx=1 tx=1 rx_dropped=0 tx_failed=0
```

With `--read-status` the ping briefly Enables, prompts an
`OperationStatus`, then Disables — useful for confirming the motor
responds with calibrated-looking values:

```bash
pixi run ping-bus --channel can0 --id 11 --read-status
# RX  OperationStatus  device=11  pos= 4.9200 rad  vel= 0.0  torque= 0.0  temp=24.0 C  fault_bits=0x00
```

The `pos` value is **motor-frame, no calibration** (the probe doesn't
load `calibration.yaml`). It's the raw absolute-encoder reading. If
it's plausibly in `[-4π, 4π]` and the motor reports temp around room
temp with `fault_bits=0x00`, the motor is healthy.

## Watch live traffic

```bash
# Print every frame in real time
candump can0

# Just framing — useful for "is anything being sent?"
candump -n 50 can0   # first 50 frames then exit
```

In a healthy bring-up with no mode controller active, you'll see
14 MIT-mode frames per tick (7 each on can0 / can1) plus the
occasional `OperationStatus` reply.

In a quiet bus (everything stopped), `candump` is silent — that's
how you confirm `on_deactivate`'s Disable made it through.

## Common findings

| `pixi run scan-bus` reports | Likely cause |
|---|---|
| `found : 0 actuator(s)` | Bus down, adapter unplugged, or motors not powered. Check `ip -d link` and the bench power. |
| `found : N < expected` | Some motors are off the bus. Trace the daisy-chain — usually a connector. |
| `warning : N ping(s) dropped at write time` | TX qdisc filling, motors not ACKing → see [Diagnose ENOBUFS](./diagnose_enobufs.md). |
| `id=X` for an ID you don't recognise | Two motors with overlapping IDs, or a leftover from a different rig. Renumber via the vendor tool. |

## See also

- [Hardware specs → Bus-bring-up checklist](../reference/hardware_specs.md#bus-bring-up-checklist)
- [Diagnose ENOBUFS](./diagnose_enobufs.md)
- [First real-hardware bringup](./first_real_bringup.md) — uses these probes as its sanity step.
