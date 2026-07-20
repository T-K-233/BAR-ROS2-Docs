---
title: Prime hybrid actuation
---

# Prime hybrid actuation

Humanoid Control Prime is the bimanual humanoid. The **waist is dropped** this version
(rigid torso, no waist drives), leaving **14 actuated DoF** — 7 per arm.
What makes Prime different from Lite is that those 14 joints live on **two
different buses, driven by two different actuator families**, yet present a
single uniform [MIT command surface](./mit_command_surface.md) to one
`controller_manager`. This page is the "why" layer for the whole Prime
bringup: the topology, how each family realizes impedance, the exact
SI-to-actuator conversions, the per-mode PD values, and the DC-sync,
switch-latency, and startup behaviors we had to solve.

## Topology — 14 DoF on two buses

Each arm has the same 7 joints. Five are **eRob** (ZeroErr CiA402 servos on
EtherCAT, through the IgH master); two — the distal wrist roll/pitch — are
**Sito** (TA40-50 MIT motors on SocketCAN).

| Joint (per arm) | Family | Bus | Address |
|---|---|---|---|
| `shoulder_pitch` | eRob | EtherCAT (master 0) | ring pos 0 / 5 |
| `shoulder_roll`  | eRob | EtherCAT | ring pos 1 / 6 |
| `shoulder_yaw`   | eRob | EtherCAT | ring pos 2 / 7 |
| `elbow_pitch`    | eRob | EtherCAT | ring pos 3 / 8 |
| `wrist_roll`     | Sito | SocketCAN `can2` | id 22 (L) / 38 (R) |
| `wrist_pitch`    | Sito | SocketCAN `can2` | id 23 (L) / 39 (R) |
| `wrist_yaw`      | eRob | EtherCAT | ring pos 4 / 9 |

So the EtherCAT ring carries **10 eRob** (positions 0-9, left arm 0-4, right
arm 5-9) and the CAN bus carries **4 Sito** wrists (ids `0x16/0x17/0x26/0x27`).
All Prime eRob are **50:1** gear. The single source of truth for this mapping
is `humanoid_bringup_prime/config/prime_hardware.yaml` (`buses`, `joints.all_joints`,
`joints.erob_slaves`, `joints.mit_joints`); the per-joint bus assignment is
emitted by `prime_description` (`robots/prime_dummy/xacro/prime_dummy.ros2_control.xacro`).

Note the **kinematic order** in `all_joints` (shoulder pitch/roll/yaw, elbow,
wrist roll/pitch/yaw) is not the **ring order** — `wrist_yaw` is eRob position
4/9 even though it sits distal of the two Sito wrists. Controllers bind to the
flat 14-joint `all_joints` list regardless of which bus carries each joint.

### Which eRob model, and why it matters a little

Two eRob models appear on Prime, distinguished only by their motor torque
constant (read each joint's model off its label; see the eRob manual §25.2):

| Model / version | `Kt` (Nm/mA, at motor) |
|---|---|
| eRob70 V4_MC2 | `0.132e-3` (the code default) |
| eRob80 V5_MC2 | `0.134e-3` (≈ 1.5% higher) |

The 1.5% `Kt` difference is negligible in practice; the **gear ratio** would
be the real lever, but every Prime eRob is 50:1, so a single conversion
serves all of them. `humanoid_bringup_prime/config/prime_hardware.yaml` can still
override `Kt`/gear per joint (`joints.erob_kt` / `joints.erob_gear`) if a model
ever differs.

## One controller_manager, two ros2_control blocks

`real.launch.py` expands the xacro with `use_fake_hardware:=false use_sim:=false`,
which emits **two concurrent `ros2_control` blocks** — `PrimeEtherCATSide`
(`ethercat_driver/EthercatDriver`, the 10 eRob) and `PrimeSitoCAN`
(`humanoid_devices_sito/SitoSystem`, the 4 Sito wrists). One `controller_manager` runs them
together and exposes a flat 14-joint list to the mode controllers. The sim path
(`mujoco.launch.py`) collapses both into one `MujocoSystem` block but presents
the identical 14 joints, so the shared controllers run unchanged.

Two bringup details are load-bearing:

- **`control_frequency` must equal the CM `update_rate` (50 Hz).** The eRob DC
  SYNC0 cycle is driven from the controller_manager's `update()` loop, not a
  separate thread. If `control_frequency` is higher than `update_rate`, SYNC0
  fires more often than process-data frames arrive, the distributed clock can't
  lock, and the drives fault. `real.launch.py` reads `update_rate` out of the
  controllers YAML and derives `control_frequency` from it so they cannot
  diverge.
- **Spawners are sequenced** (`joint_state_broadcaster` → `zero_torque_controller`
  → the inactive mode controllers). The eRob activation takes tens of seconds
  (see [Startup time](#startup-time-70-s--136-s)); running the spawners
  concurrently makes them contend on the spawner's hard-coded 20 s file lock,
  time out, and collide. Chaining them on process-exit means each acquires the
  lock alone.

## Two actuator families, two ways to realize impedance

Both families expose the same five MIT command interfaces
([position, velocity, effort, stiffness, damping](./mit_command_surface.md)),
but they implement the `τ = Kp·(q_cmd − q) + Kd·(q̇_cmd − q̇) + τ_ff` law very
differently — and that difference is the heart of the Prime control story.

### Sito: native MIT over CAN

The Sito firmware runs the MIT law directly. The host sends the desired
position, velocity, and feedforward torque in a command frame, and `Kp`/`Kd`
in a separate gains frame. Conversions (in
`humanoid_devices/humanoid_devices_sito/include/humanoid_devices_sito/sito_protocol.hpp`, TA40-50):

```
position_counts = q_cmd  · 65536 / (2π)        # 16-bit encoder, MOTOR side
velocity_counts = q̇_cmd · 65536 / (2π)
ff_current[mA]  = τ_ff / (Kt · gear)           # Kt = 9e-5 Nm/mA, gear = 51
Kp_sent = kp / 688.58                          # Nm/rad per firmware Kp unit
Kd_sent = kd / 1.125                           # Nm·s/rad per firmware Kd unit
```

The `688.58` / `1.125` divisors are a **measured** calibration of the firmware's
per-unit physical effect at the joint output. An earlier version of the code
used `500` / `0.5`, which silently ran the wrists about **1.38x too stiff** and
**2.25x over-damped**; the measured divisors fix that. (Because that section of
the source derivation is iterative, reconfirm with a torque measurement if you
need precision.)

### eRob: MIT-in-CSP (impedance emulated by loop gains)

The eRob has no per-tick stiffness/damping interface. It runs **CSP** (Cyclic
Synchronous Position, mode 8): the controller commands a target position every
tick, and the joint's *impedance* is the drive's **internal position and
velocity loop gains**. A cascaded position→velocity loop linearizes to
`kp = Kpos · Kvel` and `kd = Kvel`, which is why stiffness is expressed through
the loop gains.

The gains are manufacturer CoE objects, reachable only by **acyclic SDO** (they
are not PDO-mappable, so they cannot be a per-tick command interface):

| Object | Role |
|---|---|
| `0x2382:01` | position loop gain (`pos_reg`) |
| `0x2381:01` | velocity loop gain (`vel_reg`) |
| `0x2381:02` | velocity loop integral (held at 0 for clean impedance) |
| `0x2383`    | "Bus Regulation of PID" gate — `1` = use bus-written gains, `0` = factory |

The SI-to-register conversion (`humanoid_bringup_prime/scripts/erob_impedance_manager.py`,
`erob_gains()`), validated exactly against the ZeroErr derivation:

```
vel_reg (0x2381:01) = kd / 0.1063   ≈ 9.41 · kd       # cD = 0.1063 Nm·s/rad per LSB
pos_reg (0x2382:01) = (kp / kd) · 51.47               # cP = 0.01943, ratio only
integral (0x2381:02) = 0
```

Consequences worth remembering:

- **`kd > 0` is required for any stiffness.** Because `pos_reg` is proportional
  to `kp/kd`, a `kd` of 0 collapses both registers to 0 (true limp / zero
  torque).
- **Only `vel_reg` depends on `Kt` and gear.** The `kp/kd` ratio that sets
  `pos_reg` is model-independent, so the eRob80 vs eRob70 difference touches
  only the damping register.
- **Feedback is gear-independent.** Position and velocity are read from the
  19-bit *output* encoder, so a wrong gear/model would only mis-scale the
  *impedance magnitude*, never the position tracking.

#### The realized-vs-nominal caveat (transmission efficiency)

Load tests showed the eRob realizes roughly **0.7x** the nominal stiffness. The
clean explanation is that the manual's output-torque relation is
`joint Kt = motor Kt · gear · transmission_efficiency`, and the conversion above
omits the efficiency term (harmonic drives are ~0.7-0.85 efficient). The
manager exposes an optional `torque_efficiency` parameter (default `1.0` = off);
setting it to the measured realized/nominal ratio compensates the loss. It is
applied to **`vel_reg` only**, which provably corrects *both* the realized `kp`
and `kd` while leaving `pos_reg` (the ratio) untouched.

## Per-mode PD values

The mode controllers ([five-mode FSM](./five_mode_fsm.md)) set these per mode.
The eRob per-mode gains live in `erob_impedance_manager`'s `mode_kp`/`mode_kd`;
the Sito gains come from the active controller's `stiffness`/`damping`.

| Mode | `kp` (Nm/rad) | `kd` (Nm·s/rad) | Notes |
|---|---|---|---|
| ZERO_TORQUE | 0 | 0 | True limp on both families |
| DAMPING | 0 | 6 | Uniform across eRob + Sito (compliant fail-safe) |
| STANDBY | 20 | 2 | Position hold; setpoint seeds to the current measured position then interpolates to the pose (constant gains, no ramp) |
| LOCOMOTION | 20 | 2 (eRob, fixed) | Sito follow the policy's per-tick gains |
| REMOTE | 20 | 2 (eRob, fixed) | Sito follow the per-tick remote command |

Key asymmetry: **the eRob impedance is per-*mode* only.** SDO is acyclic and
slow, so the manager cannot retrack a per-tick varying stiffness — it writes a
fixed impedance on each mode change. In LOCOMOTION/REMOTE the four Sito wrists
honor the policy's per-tick `Kp`/`Kd`, but the ten eRob arm joints hold the
fixed mode impedance and track position in CSP.

## The eRob impedance manager

`humanoid_bringup_prime/scripts/erob_impedance_manager.py` is the bridge between the
active control mode and the eRob loop gains. It polls
`/controller_manager/list_controllers` to see which mode controller is active
(the `/control_mode` topic no longer exists) and, on each change, converts that
mode's `(kp, kd)` to loop-gain registers and writes them over the EtherLab
`ethercat download` CLI. (It uses the CLI, not the
in-process `ethercat_manager` SDO service, because the conda `libethercat` is
version-mismatched against the running kernel master.)

The one rule that keeps bringup healthy:

> **No SDO touches the bus until `/prime/joint_states` is flowing.** The
> joint_state_broadcaster only activates once every slave is fully OP, so that
> topic is the "hardware is up" signal. Mailbox SDO traffic during the staged
> DC activation disrupts the cyclic exchange and faults a slave with `0xA000`
> (EtherCAT communication error). The manager therefore stays entirely off the
> bus until the robot is up, then arms the gate (`0x2383=1`) and writes the
> first mode's gains. It resets the gate to `0` on exit so the next bringup
> activates with factory (stiff) gains.

Per-joint `Kt`/gear and the scalar `torque_efficiency` are parameters, wired
from `prime_hardware.yaml`.

## Two things we solved

### PD-switch latency (3.6 s → 0.46 s)

**Symptom:** switching modes (e.g. DAMPING ↔ STANDBY) propagated visibly across
the arms — the left shoulder responded immediately, the right arm seconds later.

**Mechanism:** in OP each CoE SDO transfer is **cycle-gated** — the master
advances the SDO state machine roughly once per 50 Hz cycle, so one object takes
~120 ms (~6 cycles). A mode switch writes 3 objects to 10 slaves = **30 SDOs**,
and the manager did them strictly in ring order, so the total was ~3.6 s with
the tail-of-ring (right arm) carrying the full cumulative delay.

**Fix:** the IgH master pipelines outstanding mailbox transfers across slaves,
so issuing the per-slave writes **concurrently** (one worker per slave) collapses
the wall-clock from sum-of-slaves to roughly one slave's time — measured
**~0.46 s, all slaves within ~40 ms** of each other. Controlled by the
`parallel_sdo` parameter (default on); set it false to reproduce the sequential
baseline.

### Startup time (70 s → 13.6 s)

**Symptom:** bringup took ~70 s and logged ~7 transient `0xA000` fault/recover
cycles before stabilizing.

**Mechanism:** a slave reaches EtherCAT OP only after the master's **DC drift
compensation converges**, which is cycle-count bound. The ICube
`ethercat_driver`'s `on_activate` bring-up loop paced its `update()` at
`control_frequency` (50 Hz), so convergence took ~7 s per slave (the domain
working-counter climbed one slave at a time, ~7 s apart). The `0xA000` faults
were collateral: each newly-joining slave briefly glitched the domain and
starved the others' output-watchdog.

**Fix:** a small patch runs the bring-up loop at **1 kHz**, independent of
`control_frequency`. DC converges ~5x faster and the watchdog stays fed, so
bringup drops to **~13.6 s with zero faults** — and there is **no steady-state
change** (DC SYNC0 still runs at `control_frequency`, and the CM read/write loop
takes over at `update_rate` once activation returns). The patch is a local
modification to the ICube `ethercat_driver_ros2` that `bar.repos` pins
(`ethercat_driver/src/ethercat_driver.cpp`); to survive a fresh `vcs import` it
must land in a Berkeley fork that `bar.repos` then pins (TODO).

## Fault / status reference

The CiA402 statusword and eRob error codes you will actually see on Prime:

| Code | Meaning |
|---|---|
| statusword `5687` | Operation Enabled (healthy, running) |
| statusword `4616` | Fault state — on Prime almost always the DC-sync / comms family |
| error `0xA000` | EtherCAT communication error (see startup + impedance-manager notes above) |
| error `0x8500` | Position error exceeds limit |
| error `0x8400` | Velocity error exceeds limit |
| error `0x8130` | CAN heartbeat error |

Read the live error code with `ethercat upload -pN 0x603F 0` and the stored
history with `0x1003`. Symptom-first entries are on the
[Troubleshooting](../reference/troubleshooting.md) page.

## See also

- [Five-mode FSM](./five_mode_fsm.md) — the mode controllers and flat `joy_teleop` switching.
- [MIT command surface](./mit_command_surface.md) — the shared 5-interface model.
- [Calibrate the Prime arms](../how_to/calibrate_prime_erob.md) — software
  calibration (direction + homing offset), single-source in
  `prime_calibration.yaml`, folded into the eRob configs at launch and read by
  `SitoSystem` for the wrists.
- [First real-hardware bringup](../how_to/first_real_bringup.md).
