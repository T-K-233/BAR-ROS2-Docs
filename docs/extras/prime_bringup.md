# Prime real-hardware bringup

Recipe for bringing the physical **Prime** up on real hardware — the eRob
arm joints over **EtherCAT** plus the Sito wrists over **SocketCAN**, running
concurrently. It is the Prime counterpart of
[First real-hardware bringup](../how_to/first_real_bringup.md) (which covers
Lite), and it assumes you have already built the EtherCAT / Prime packages
(see [Installation → Build from source](../getting_started/installation.md)).

:::warning[Experimental — bring-up is still in progress]
Prime real-hardware support is not yet at Lite's maturity. A single eRob
(`left_wrist_yaw`) has been brought up and jogged on silicon; the full
multi-joint bus-split is still being commissioned. Treat the steps below as
the current best-known procedure, not a turnkey flow, and expect to fall back
to the single-bus / diagnostic modes while bringing a fresh robot up.
:::

## How Prime differs from Lite

Lite is homogeneous (Robstride on two SocketCAN buses). Prime is **hybrid**:
the expansion of `prime_dummy.urdf.xacro` with `use_fake_hardware:=false
use_sim:=false` emits **two concurrent `<ros2_control>` blocks**, and
`controller_manager` runs them together, exposing one flat **14-joint** list
to the controllers (the waist is dropped in this version):

| Block | Plugin | Joints | Bus |
|---|---|---|---|
| `PrimeEtherCATSide` | `ethercat_driver/EthercatDriver` | 10 eRob arm joints (CiA402 / CSP) | EtherCAT, via the IgH master |
| `PrimeSitoCAN` | `humanoid_devices_sito/SitoSystem` | 4 Sito wrist joints | one SocketCAN bus (`can2`) |

:::note[Hybrid command surface]
The 10 eRob joints are CiA402 and expose **no stiffness/damping interfaces** —
they are held in position (CSP), and their impedance is set out-of-band by
writing the drive's internal loop gains per mode (see
[eRob impedance per mode](#erob-impedance-per-mode) below). Only the 4 Sito
wrists (`mit_joints`) expose the full MIT command surface, so the MIT-style
`humanoid_controllers` fully activate over the wrists until the controllers are
reworked for the hybrid. The bus / description / controller_manager wiring is
correct regardless.
:::

## Bus topology

From `humanoid_bringup_prime/config/prime_hardware.yaml` — the single source
of truth for how this robot is wired:

| Joint | Bus / address | Joint | Bus / address |
|---|---|---|---|
| `left_shoulder_pitch` | eRob ring pos 0 | `right_shoulder_pitch` | eRob ring pos 5 |
| `left_shoulder_roll`  | eRob ring pos 1 | `right_shoulder_roll`  | eRob ring pos 6 |
| `left_shoulder_yaw`   | eRob ring pos 2 | `right_shoulder_yaw`   | eRob ring pos 7 |
| `left_elbow_pitch`    | eRob ring pos 3 | `right_elbow_pitch`    | eRob ring pos 8 |
| `left_wrist_roll`     | Sito id 22 (`can2`) | `right_wrist_roll` | Sito id 38 (`can2`) |
| `left_wrist_pitch`    | Sito id 23 (`can2`) | `right_wrist_pitch`| Sito id 39 (`can2`) |
| `left_wrist_yaw`      | eRob ring pos 4 | `right_wrist_yaw`      | eRob ring pos 9 |

So each arm is 5 eRob (the three shoulder DOF, elbow, and wrist yaw) + 2 Sito
(wrist roll and pitch) = 7, for 10 eRob + 4 Sito = 14 total.

## Prerequisites

- **Built with the EtherCAT / Prime packages.** The default source build
  *skips* `ethercat.*` and `humanoid_bringup_prime`. To include them, install
  the IgH EtherLAB master from source on the host, then drop the
  `--packages-skip-regex` filter — see
  [Installation → Build from source](../getting_started/installation.md).
- **The IgH EtherCAT master is running and the drives are powered.** The master
  is a *host system service* (`ethercatctl` / systemd) and is **not** started
  by the launch — `ethercat_driver` only connects to it (via `master_id`, `0`
  by default). See [Step 1](#step-1--start-and-verify-the-ethercat-master).
- **The Sito CAN bus is up.** `can2` at the 1 Mbit Robstride/Sito bitrate.
- **eRob software calibration is present.** `real.launch.py` folds
  `prime_calibration.yaml` (per-joint `direction` + `homing_offset`) into each
  eRob's generated slave config at launch — no drive-NVM writes. Generate it
  with [Calibrate the Prime arms](../how_to/calibrate_prime_erob.md).

## Step 1 — Start and verify the EtherCAT master

Start the host master (skip if it is already a running systemd service), then
confirm it sees every eRob slave:

```bash
sudo ethercatctl start          # or: sudo systemctl start ethercat
ethercat master                 # expect one master, link UP
ethercat slaves                 # expect the eRob drives at ring positions 0..9
```

Each eRob should appear at its ring position from the table above. If slaves
are missing, it is a cabling / power / master-config problem — fix it here
before launching, because `ethercat_driver` will not enumerate what the master
cannot see.

## Step 2 — Bring up the Sito CAN bus

Same as a Lite bus, on the interface Prime uses for the wrists:

```bash
sudo ip link set can2 down 2>/dev/null
sudo ip link set can2 up type can bitrate 1000000
```

## Step 3 — Launch the bringup

```bash
ros2 launch humanoid_bringup_prime real.launch.py
```

That defaults to `backends:=all` (both buses) and bakes in
`use_fake_hardware:=false use_sim:=false`. Useful arguments:

| Arg | Default | Purpose |
|---|---|---|
| `backends` | `all` | `all` (both buses) · `ec` (eRob/EtherCAT only) · `can` (Sito/CAN only). The single-bus modes spawn only `joint_state_broadcaster` — for calibration / diagnostics. |
| `enable_mode_manager` | `true` | Launch the `mode_manager` FSM. |
| `enable_erob_impedance` | `true` | Spawn `erob_impedance_manager` (eRob loop gains per `/control_mode`). Pass `false` to isolate startup races or fall back to factory-gain (stiff) eRob. |
| `enable_gamepad` | `true` | Spawn `joy_node`. Pass `enable_gamepad:=false` for headless / CI bringups. |
| `calibration_file` | bundled `prime_calibration.yaml` | Per-joint eRob software calibration, folded at launch. |
| `hardware_config` | bundled `prime_hardware.yaml` | `buses:` + `joints.all_joints`. |

:::note[eRob SYNC0 and `control_frequency`]
The eRob distributed-clock SYNC0 cycle (`control_frequency`) **must** equal the
`controller_manager` `update_rate` (50 Hz). `ethercat_driver` sends PDOs and
syncs the DC clock from the CM `update()` loop, not a dedicated thread, so a
mismatch makes the clock never lock → CiA402 **Fault 4616**. `real.launch.py`
reads `update_rate` from the same controllers YAML the CM loads and passes it as
`control_frequency`, so they cannot diverge — do not override one by hand.
:::

## Step 4 — What to expect

- The eRob reach EtherCAT **OP** one at a time. Historically this took ~70 s
  with cycling `0xA000` faults; with the bring-up pacing fix (now the default
  in the pinned `ethercat_driver`) it is **~13.6 s with zero faults**. See
  [Troubleshooting → Prime eRob bringup](../reference/troubleshooting.md) if it
  stalls.
- The controller spawners are **sequenced** (`joint_state_broadcaster` →
  `zero_torque_controller` → the inactive `damping` / `standby` /
  `remote_policy` controllers). They serialize on a file lock; chaining them on
  process-exit lets the first wait out the eRob activation alone and the rest
  run fast.
- `/joint_states` is published as **`/prime/joint_states`**.

## Step 5 — Verify

```bash
ros2 topic hz /prime/joint_states     # 14 joints at ~50 Hz
ros2 control list_controllers         # joint_state_broadcaster + zero_torque active; rest inactive
ros2 topic echo /control_mode         # mode_manager state, once a mode is requested
```

## Single-bus / diagnostic modes

When one bus misbehaves, bring the other up on its own. These spawn only
`joint_state_broadcaster` (the joint-consuming controllers claim the full
14-joint list, which cannot fully activate with a bus absent):

```bash
ros2 launch humanoid_bringup_prime real.launch.py backends:=ec    # eRob/EtherCAT only
ros2 launch humanoid_bringup_prime real.launch.py backends:=can   # Sito/CAN only
```

`backends:=can` is also what the Sito calibration sweep uses, so the eRob's
EtherCAT activation and DC faults cannot stall the Sito command/feedback path.

## eRob impedance per mode

eRob impedance lives in the drive's internal CSP loop as CoE objects that are
SDO-only (not PDO-mappable, so not a per-tick command interface).
`erob_impedance_manager` watches `/control_mode` and writes each eRob's loop
gains (`kp`/`kd` → `0x2382`/`0x2381`, gate `0x2383`) for the active mode via the
EtherLab `ethercat` CLI. The mode controllers keep commanding eRob *position*
(CSP); these gains decide whether a joint holds, damps, or goes limp. Pass
`enable_erob_impedance:=false` to drop this path while isolating startup races.

If a mode switch propagates slowly across the arm (one joint at a time), keep
`parallel_sdo` enabled — see
[Troubleshooting → Prime mode switch](../reference/troubleshooting.md).

## Common Prime bring-up failures

All in [Troubleshooting](../reference/troubleshooting.md):

- **eRob bringup takes ~70 s with repeated `0xA000` faults** — the DC
  convergence pacing issue (fixed by default; see the entry if it recurs).
- **eRob faults `4616` immediately on enable** — `control_frequency` ≠
  `update_rate` (see the [SYNC0 note](#step-3--launch-the-bringup) above).
- **Mode switch propagates slowly across the arm** — keep `parallel_sdo` on.

## See also

- [Calibrate the Prime arms (eRob + Sito)](../how_to/calibrate_prime_erob.md) — the software-offset sweep this bringup folds in
- [Prime hybrid actuation](../concepts/prime_hybrid_actuation.md) — why the eRob/Sito split looks the way it does, and the PD → loop-gain conversion
- [First real-hardware bringup](../how_to/first_real_bringup.md) — the Lite equivalent this mirrors
- [Launch arguments](../reference/launch_args.md) — every bringup launch and its args
