---
title: Diagnose ENOBUFS / TX drops
---

# Diagnose ENOBUFS / TX drops

`Network is down` / `No buffer space available` warnings in the
controller_manager log mean the kernel's CAN TX queue is full and
frames are being dropped at write time. This page is the runbook
for finding and fixing the root cause.

## The symptom

```
[humanoid_drivers_socketcan]: CAN write() returned -1 (errno=No buffer space available) for id=0x017FFF0B
[humanoid_drivers_socketcan]: CAN write() returned -1 (errno=No buffer space available) for id=0x017FFF15
...
```

Plus a `/safety_status` message with `FLAG_TX_QUEUE_OVERRUN` set
(open a `pixi shell` first so `ros2` is on PATH):

```bash
cd humanoid_control_ws && pixi shell
ros2 topic echo /safety_status
# level: 2     # FAULT
# flags: 4     # FLAG_TX_QUEUE_OVERRUN = 1 << 2
# source: humanoid_devices_robstride/can0
```

## Why it happens

CAN frames must be **acknowledged on the bus** by at least one
receiver. If a frame goes unacknowledged the transmitter retries it
indefinitely; the kernel TX qdisc (default `txqueuelen=10`) fills up;
new `write()` calls return `ENOBUFS`.

The plugin's I/O thread can't drain the qdisc faster than the wire
allows, and the RT writer keeps producing frames every tick. Net
result: dropped frames, including the all-important `Enable` frames
at activation.

**The most common cause of unacknowledged frames is motor power being
off.** No motors on the bus → no ACKs → qdisc fills. Easy mistake to
make on the bench; the kernel CAN socket opens happily without
motors powered.

## Step 1 — Check motor power

Walk to the robot. Power switch on. E-stop released. 24 V LED lit on
each motor.

```bash
# Quick read-only probe to confirm motors are responding
pixi run scan-bus --channel can0
pixi run scan-bus --channel can1
# Should report 7 motors on each bus, no ENOBUFS warnings in the output.
```

If the scan itself reports `tx_dropped > 0`, motors are
still off the bus. Don't proceed until that scan is clean.

## Step 2 — Check the kernel CAN state

```bash
ip -d link show can0
ip -d link show can1
```

Look for:
- `state UP` (not DOWN)
- `can state ERROR-ACTIVE` (not BUS-OFF / ERROR-PASSIVE)

If `BUS-OFF`: power-cycle the USB-to-CAN adapter. The Linux kernel
won't auto-recover from BUS-OFF without `restart-ms` set, which we
intentionally leave off (silent self-recovery hides real problems).

If `ERROR-PASSIVE`: lots of errors lately. Either many missing acks
(power), or a bad wire (continuity test).

## Step 3 — Verify the host-side queue depth

```bash
ip link show can0 | grep qlen
# qlen 10        ← default
```

`qlen=10` is fine for a healthy bus, but tight if the host is
periodically slow draining (USB hub contention, etc). If raising
queue depth lets the system survive transient slowness:

```bash
sudo ip link set can0 txqueuelen 100
sudo ip link set can1 txqueuelen 100
```

This is a runtime change — not persisted across reboots. To make it
permanent on Ubuntu, add a systemd-networkd or netplan stanza, or
script it into the launch's pre-step.

:::warning[Big qdisc != fix]
Raising `txqueuelen` masks symptoms when the host is the bottleneck,
but doesn't help when motors aren't ACKing. If `ENOBUFS` still fires
after `txqueuelen=1000`, the qdisc isn't the problem — go back to
Step 1.
:::

## Step 4 — Look at the bus library counters

The plugin's safety publish keeps two relevant counters. From the
log lines or by tracing the topic in the future (currently TODO —
not all are surfaced):

| Counter | Meaning |
|---|---|
| `tx_count` | total frames successfully written to the kernel |
| `tx_failed` | total `write()` calls that returned `< sizeof(can_frame)` |
| `rx_count` | total frames the I/O thread read |
| `rx_dropped` | RX SPSC ring overflow (controller_manager not keeping up) |

If `tx_failed` is climbing during a steady-state operation,
something is repeatedly dropping. If it's high at activation only
and quiet afterwards, the Enable burst was the issue.

## Step 5 — Reduce the per-tick load

If you've raised qdisc to 1000 and still hit ENOBUFS, the
controller_manager might be writing too fast for the wire. Lower
the update rate in `lite_controllers.yaml`:

```yaml
controller_manager:
  ros__parameters:
    update_rate: 50   # was 100? drop to 50; or to 25 in extreme cases
```

For 14 joints at 50 Hz, the wire carries 700 MIT frames/sec total
(350 per bus). Robstride at 1 Mbps has plenty of bandwidth headroom
on paper; the limit is usually USB-side latency to the adapter
firmware, not raw bandwidth.

## Step 6 — Verify the adapter

USB-to-CAN adapters vary in TX FIFO depth:

| Adapter | TX FIFO depth |
|---|---|
| CANable v2.0 (gs_usb) | small (a few frames) |
| Kvaser USBcan series | larger (hundreds) |
| PCAN-USB Pro | larger |

If you're on a gs_usb adapter and dropping at high rates, no kernel
queue tuning will fix it — the adapter's internal FIFO is your
bottleneck. Either drop the rate or upgrade the adapter.

## Decision tree

```
ENOBUFS warnings observed
├── pixi run scan-bus reports 0 motors → motor power off → fix power, relaunch
├── pixi run scan-bus reports motors but ENOBUFS persists at activation only
│   └── Burst-on-Enable. Drop activate-time WriteParameter calls (already done
│       in our plugin via write_firmware_limits=false default). If recurring,
│       raise txqueuelen or stagger Enables.
├── ENOBUFS during steady-state operation
│   ├── txqueuelen=1000 fixes it → USB hub contention; tune your USB topology
│   └── still drops at 1000 → reduce controller_manager.update_rate
└── bus state BUS-OFF → power-cycle the adapter, then back to top
```

## See also

- [Reference → Troubleshooting](../reference/troubleshooting.md) — quick lookup of related symptoms.
- [Probe actuators on a CAN bus](./probe_can_bus.md) — the discover / ping path.
- [Concepts → Safety pipeline](../concepts/safety_pipeline.md) — why ENOBUFS appears as a safety flag.
