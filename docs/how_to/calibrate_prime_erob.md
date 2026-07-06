# Calibrate the Prime arms (eRob + Sito)

Per-physical-robot recipe: regenerate `humanoid_bringup_prime/config/prime_calibration.yaml`
so each joint's encoder zero maps to the URDF's joint zero. One file holds all 14
joints — the 10 eRob (ZeroErr, EtherCAT) arm joints and the 4 Sito (CAN) wrists — and
the **same** `calibrate_erob` sweep tool calibrates both. Same idea as
[Calibrate the zero pose](./calibrate_zero_pose.md) for Lite.

The eRob is the involved case — a stiff CiA402 servo on EtherCAT, so "make it limp"
works differently — and is covered first. The Sito wrists are backdrivable MIT motors,
limp by default; see [Calibrate the Sito wrists](#calibrate-the-sito-wrists) below.

## What the calibration does

The eRob output encoder is absolute (it keeps its zero across power cycles) with a
factory zero; the URDF defines a different joint zero. The offset bridges them,
exactly as on Lite:

```
joint_pos = direction * (raw_pos - homing_offset)
```

`direction` (plus/minus 1) is a wiring fact; `homing_offset` is per-physical-robot.
The full derivation — `homing_offset = 0.5 * ((min - lower) + (max - upper)) * direction`,
averaged over both mechanical stops — is on the
[Calibration math](../concepts/calibration_math.md) page.

The Lite/eRob difference is **where the offset is applied**. Lite owns its hardware
interface, so it subtracts `homing_offset` in `read()`/`write()`. The eRob runs on the
third-party `ethercat_driver`, which we do not fork — so `scripts/fold_calibration.py`
folds the offset into each joint's PDO `factor`/`offset` in a generated per-slave
config, and `real.launch.py` hands that to the xacro at launch via the
`erob_config_dir` argument. No drive-NVM writes; the calibration stays in one
git-tracked YAML.

## How the eRob differs from Lite

- **No MIT zero-torque.** The eRob runs CSP (Cyclic Synchronous Position); it has no
  stiffness/damping command interface. To hand-sweep, we turn it into a **velocity
  damper** by writing its internal loop gains.
- **The PID gate — `0x2383`.** Object `0x2383` ("Bus Regulation of PID", default 0 =
  off) gates whether bus-written loop gains are applied. **It must be set to 1 first**,
  or writes to the gain objects are silently ignored and the joint stays stiff. This is
  the single most common reason "the limp does nothing".
- **Damped-limp, one joint at a time.** Set position-loop gain `0x2382:01` to 0 (no
  stiffness) and velocity-loop integral `0x2381:02` to 0 (no spring-back), but **keep**
  the velocity-loop gain `0x2381:01` (damping) so gravity gives a slow controlled
  descent instead of freefall. On a heavy arm, limp one joint while the others stay
  held — `scripts/erob_limp_joint.sh` does exactly this (snapshot, gate on, kp/ki to 0,
  sweep, restore on exit).

## Prerequisites

- The arms are **supported** (jig, table, or a helper). Damping limits the *speed* of a
  fall, not the position — the shoulder still holds the whole arm.
- The IgH EtherCAT master is running and the drives are powered. See
  [Prime real-hardware bringup](../extras/prime_bringup.md).
- e-stop in reach.

## Step 1 — Bring up the chain and the tracker

Bring the eRob drives to CSP Operation-Enabled with `calibrate.launch.py`. Pass
`backends:=ec` to bring up only the EtherCAT arms (no Sito); the default `backends:=all`
brings up everything. Staged activation is slow — roughly 6-7 s per drive, serial, in
the IgH/eRob handshake — so a 10-drive chain takes about 70 s. That **activation** cost
is fixed (not tunable: it is the per-slave handshake). Note this is separate from
`control_frequency`, which *does* matter — but for steady-state DC sync, not activation
time (see [Gotchas](#gotchas)).

The launch also spawns the `joint_state_broadcaster` (so `/prime/joint_states` flows)
and the `calibrate_erob` tracker:

```bash
ros2 launch humanoid_bringup_prime calibrate.launch.py backends:=ec \
  output:=~/prime_calibration.yaml \
  prior:=$(ros2 pkg prefix humanoid_bringup_prime)/share/humanoid_bringup_prime/config/prime_calibration.yaml
```

`prior:=...` carries already-calibrated joints (the Sito wrists, or the other arm)
through unchanged, so a partial run still writes a complete file. `calibrate_erob`
discovers the eRob joints from the URDF `ec_module`s, reads each joint's `lower`/`upper`
from the kinematic limits, and tracks per-joint `min`/`max` of `/prime/joint_states`
with a live readout.

## Step 2 — Damped-limp and sweep each joint

For each ring position, support the joint, then:

```bash
ros2 run humanoid_bringup_prime erob_limp_joint <ring_pos>      # e.g. 4
```

The joint goes damped-limp (the read-back prints `Kp=0`, confirming the `0x2383` gate
worked). Sweep it firmly to **both** mechanical stops — watch the tracker's `sweep`
grow past about 0.5 rad so it is not skipped — return near neutral, and press Enter to
re-hold. If a joint is too stiff to move, pass a smaller damping value as a second
argument. Work distal to proximal; do the shoulder last.

When every joint is swept, **Ctrl-C the tracker** — it writes the YAML and flags any
joint with too small a sweep (skipped, prior kept) or `abs(homing_offset) > pi` (a
`direction` sign flip — set `-1` and re-sweep that joint).

## Step 3 — Apply and verify

Copy the reviewed file over `humanoid_bringup_prime/config/prime_calibration.yaml`.
`real.launch.py` folds it into per-joint configs automatically at launch. To verify the
sign end-to-end, fold it, re-launch, and move one joint to a known stop — at the stop,
`/joint_states` should read that joint's URDF limit.

A good cross-check on a symmetric robot: the two arms' offsets should mirror each other
(a joint whose limits are mirrored, like `shoulder_roll`, gets a sign-flipped offset).

## Calibrate the Sito wrists

The 4 Sito wrists (`left`/`right` `wrist_roll` + `wrist_pitch`) use the **same**
`calibrate_erob` tool and the **same** `prime_calibration.yaml` — it discovers them from
the `humanoid_devices_sito/SitoSystem` block (by `can_id`) alongside the eRob. Two differences:

- **Limp is free.** A Sito is an MIT motor; with no command controller active its gains
  default to zero, so it is backdrivable out of the box — no gain-gate dance.
- **Sweep on an isolated CAN loop.** Run `backends:=can` so only the Sito come up: the
  eRob's ~70 s activation and DC handshake do not interfere, and there are no stiff arm
  joints to fight. Seed the eRob offsets through unchanged with `prior:=...` so the
  single-bus run still writes a complete 14-joint file.

```bash
ros2 launch humanoid_bringup_prime calibrate.launch.py backends:=can \
  output:=~/prime_calibration.yaml \
  prior:=$(ros2 pkg prefix humanoid_bringup_prime)/share/humanoid_bringup_prime/config/prime_calibration.yaml
```

Hand-sweep each wrist to both stops (the live readout tracks them), Ctrl-C, review, copy
over `prime_calibration.yaml`, and `colcon build --packages-select humanoid_bringup_prime`.
Unlike the eRob, the Sito read `direction` **and** `homing_offset` straight from this
file (`SitoSystem::load_calibration`) — so a flipped wrist is a one-line edit.

### Flipping a direction without re-sweeping

If a joint tracks backwards in viz, flip its `direction` (`+1` to `-1`) and recompute the
offset with the URDF limits:

```
offset_new = offset + (lower + upper)
```

For a symmetric joint (`lower = -upper`, e.g. the wrists) the offset is unchanged; for an
asymmetric one (e.g. `shoulder_roll`, `elbow_pitch`) it shifts. Then
`colcon build --packages-select humanoid_bringup_prime` — no source rebuild; the eRob fold and
`SitoSystem` both re-read the file at launch. This works for any joint, eRob or Sito.

## eRob bus-split (hardware-confirmed)

Both arms sit on one EtherCAT ring, 0-based and contiguous. The fifth arm eRob is
`wrist_yaw` (not `wrist_roll`); `wrist_roll` and `wrist_pitch` are the small Sito (CAN)
wrists, not on the eRob chain.

| pos | joint | pos | joint |
|---|---|---|---|
| 0 | left_shoulder_pitch | 5 | right_shoulder_pitch |
| 1 | left_shoulder_roll | 6 | right_shoulder_roll |
| 2 | left_shoulder_yaw | 7 | right_shoulder_yaw |
| 3 | left_elbow_pitch | 8 | right_elbow_pitch |
| 4 | left_wrist_yaw | 9 | right_wrist_yaw |

There is no waist this version — the 3 former waist joints are `fixed` in the URDF, so
the ring is exactly these 10 drives.

## Gotchas

- **"Limp does nothing / joint stays stiff"** — `0x2383` was not set to 1, so the
  drive ignored the gain writes. `erob_limp_joint.sh` sets it first and the read-back
  shows `Kp=0` when it took.
- **`control_frequency` must equal the controller_manager `update_rate`.**
  `ethercat_driver` sends PDOs and syncs the DC clock from the CM `update()` loop (there
  is no separate EtherCAT thread), so the DC SYNC0 cycle — set by `control_frequency` —
  must match the loop rate. Mismatched (e.g. `control_frequency=1000` against a 50 Hz
  loop) the drives see SYNC0 firing far more often than frames arrive and fault in steady
  state (status `4616`/`520`, domain WC collapses). `real.launch.py` derives
  `control_frequency` from the controllers YAML `update_rate` so they cannot diverge; if
  you set it by hand, keep them equal. This is the usual cause of "eRob hold for a moment,
  then fault".
- **Keep DC enabled.** The eRob also faults (`4616`) in free-run CSP with DC disabled —
  do not turn DC off to "fix" timing; match `control_frequency` instead. Damped-limp
  keeps the drive in CSP/Operation-Enabled the whole time, so calibration is unaffected.
- **`wrist_roll`/`wrist_pitch` are Sito** — calibrate them with the same tool via
  [Calibrate the Sito wrists](#calibrate-the-sito-wrists) (`backends:=can`), not the eRob
  limp procedure.
