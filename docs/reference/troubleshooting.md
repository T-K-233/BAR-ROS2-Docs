# Troubleshooting

A flat list of the symptoms we've actually seen, in rough frequency
order. Each entry has the one-line diagnosis and the page that
explains it. The intent is to short-circuit the "ah, that one again"
moment.

## Bringup boots, but every joint reads exactly 0.0

**Diagnosis**: the actuators are not Enabled — usually because the
Enable frame was dropped before the motors could ACK.

**Why**: `RobstrideSystem::on_activate` sends one `Enable` per joint,
back-to-back into the kernel TX qdisc (default `txqueuelen=10`). With
14 joints and a few extra frames, the qdisc can fill if the motors
aren't ACKing TX. No ACK → no qdisc drain → ENOBUFS → frames dropped.
The motors miss their Enable and never come out of disabled state.

**The most common cause of no ACKs is motor power being off.**

**Fix**:
1. Confirm motor power. Walls and 24 V supply both on; e-stop released.
2. Re-launch. The Enable burst should now succeed.

If power is verified on but ENOBUFS persists, see [Diagnose ENOBUFS](../how_to/diagnose_enobufs.md).

## `Failed to open SocketCAN interface 'canN'`

**Diagnosis**: the CAN interface isn't up (`LOWER_UP` / `state UP`).

**Why**: `ip link set canN down` on reboot, or USB adapter was hot-plugged
after the kernel last saw it.

**Fix**: bring the bus up at the Robstride bitrate (1 Mbps):

```bash
sudo ip link set can0 down 2>/dev/null
sudo ip link set can0 up type can bitrate 1000000
# Same for can1
```

The plugin's `SIOCGIFFLAGS` guard catches this case explicitly so the
error log is one line — no silent hang.

## `Loaded calibration_file '...' (0/N joints matched)`

**Diagnosis**: the YAML keys don't line up with any of the joint names
the plugin's seeing from URDF.

**Why**: usually one of:
- The URDF was renamed, but `calibration.yaml` is from an older revision.
- The path resolved to the wrong file (typo, stale install share).
- You hand-edited the YAML and broke a key.

**Fix**: open the file, compare keys against
`humanoid_control_lite_controllers.yaml`'s `joints:` list. They must match
character-for-character. Or regenerate the file via
[Calibrate the zero pose](../how_to/calibrate_zero_pose.md) — the
output uses live URDF names.

## Launch dies with "`joy_dev:=...` does not exist"

**Diagnosis**: `enable_gamepad:=true` is the default, and the bringup
hard-fails when the resolved `joy_dev` path is missing.

**Fix**, in order of likelihood:

1. **Gamepad not plugged in.** The launch's error message
   distinguishes "device path missing but other `js*` exist" from
   "no joystick at all" so you can tell at a glance.
2. **Wrong device number.** The error message lists every
   `/dev/input/js*` the launch could see; pass
   `joy_dev:=/dev/input/jsN` (matching one of them) on the launch
   command line.
3. **Headless / CI bringup.** Pass `enable_gamepad:=false` and switch
   controllers directly with
   `ros2 control switch_controllers --activate <name> --deactivate <name>`
   instead.

## Gamepad is connected and `cat /dev/input/js0` shows data, but `/joy` never publishes

**Diagnosis**: `joy_node` comes up and registers a `/joy` publisher but
emits **zero messages**, so `joy_teleop` never sees a button — even
though the pad is paired and `cat /dev/input/js0` streams bytes when you
press it.

**Why**: the ROS 2 `joy` node is **SDL2-based**, and SDL2 reads
joysticks through the **evdev** interface (`/dev/input/event*`), *not*
the legacy joystick interface (`/dev/input/js*`). Those are different
device nodes with different permissions:

- `jsN` is usually world-readable (`other::r--`) — so `cat
  /dev/input/jsN` works for any user and makes the pad *look* fine.
- `eventN` is `root:input crw-rw----` with **no world read**. Access is
  granted only to `root`, the **`input` group**, and — via a `uaccess`
  ACL — whoever owns the **active local login seat** (normally the GUI
  user, *not* an SSH session).

So when you launch over SSH or with no desktop session, your user is
neither in `input` nor the seat owner → SDL2 can't open `eventN` → no
joystick → `/joy` stays silent. It often "worked yesterday" because you
were sitting at the desktop then and the seat ACL covered you.

Confirm it — find your pad's `eventN` via `/dev/input/by-id/`
(`...-event-joystick -> ../eventN`):

```bash
getfacl -p /dev/input/event5
#   user:gdm:rw-   group::rw- (input)   other::---     <- granted to gdm, not you
[ -r /dev/input/event5 ] && echo CAN-READ || echo NO-READ-PERM
id | grep -q '(input)' && echo in-input-group || echo NOT-in-input-group
```

**Fix**: add your user to the `input` group — persistent across reboots
and independent of the GUI seat:

```bash
sudo usermod -aG input "$USER"
```

Then **start a fresh login** for it to take effect (new terminal / new
SSH session, or reboot). Verify `id` now lists `input`, relaunch, and
`ros2 topic hz /joy` should show ~20 Hz while you hold a button.

This is distinct from the `joy_dev` error above: there the device path
is *missing*; here it *exists and reads fine with `cat`*, and only the
SDL2/evdev permission is wrong.

**Headless / CI**: skip the pad with `enable_gamepad:=false` and switch
controllers directly with `ros2 control switch_controllers` instead.

## ENOBUFS / "Network is down" warnings during bringup

**Diagnosis**: kernel TX qdisc full, frames being dropped at write
time. Almost always = motors not ACKing.

**Why**: motor power off (most common), bus stuck `BUS-OFF`, or
hardware adapter overload at very high frame rates.

**Fix**:
1. **Motor power off** — power on, re-launch. Resolves 99% of cases.
2. **`BUS-OFF`** — `ip -d link show canN` will say so. Power-cycle
   the USB-to-CAN adapter.
3. **High-rate overload** — only relevant with many joints + tight
   update_rate. Lower `controller_manager.update_rate` in
   `humanoid_control_lite_controllers.yaml`, or bump `sudo ip link set canN
   txqueuelen 100` (default 10).

Full walk: [Diagnose ENOBUFS](../how_to/diagnose_enobufs.md).

## `/safety_status` shows `flags != 0`

**Diagnosis**: the plugin observed an actuator-side fault on at least
one tick. Even a single bad frame trips a bit until `on_activate`
clears it.

The bit table:

| Flag | Meaning |
|---|---|
| `FLAG_BUS_OFF` | Kernel CAN socket open failed (sticky — survives until configure). |
| `FLAG_RX_TIMEOUT` | A joint went silent for > `rx_timeout_ms`. |
| `FLAG_TX_QUEUE_OVERRUN` | Bus library's outbound ring filled (RT producer faster than I/O thread). |
| `FLAG_MOTOR_FAULT` | Robstride status / fault report reported a non-OK condition. |
| `FLAG_TEMPERATURE_LIMIT` | Specifically overtemp, surfaced separately for visibility. |
| `FLAG_INVALID_FRAME` | Frame on the bus that we couldn't parse (wrong comm-type, wrong DLC). |

**Fix**: see [Recover from a fault](../how_to/recover_from_fault.md).

## A gamepad button (or a switch) doesn't change the controller

**Diagnosis**: there is no FSM and no gating any more. `joy_teleop` maps
each button directly to `/controller_manager/switch_controller`, and every
transition is allowed from every state, so a button that does nothing is
almost always a config or load problem — not a rejected transition.

**Why**: switching is flat and `BEST_EFFORT` — activate one controller,
deactivate its siblings. If nothing happens, either `joy_teleop` isn't
running / isn't receiving `/joy`, the button map in the `joy_teleop_*.yaml`
doesn't match the pad, or the target controller was never loaded.

**Fix**: read the current state and switch by hand to confirm the target
controller exists:

```
ros2 control list_controllers
ros2 control switch_controllers --activate <name> --deactivate <name>
```

If the manual switch works but the button doesn't, the problem is in
`joy_teleop` (`/joy` silent, or the wrong button index in the YAML). Note
that `/control_mode` no longer exists — read the active mode from
`ros2 control list_controllers`.

## Spawner times out waiting for `/controller_manager/list_controllers`

**Diagnosis**: the controller_manager process isn't fully up yet.
Normal on a cold boot; usually clears within ~2 s. If the wait
exceeds ~10 s, something is wrong with the launch (hardware plugin
crashed, ROS domain mismatch, robot_state_publisher hung on a stale
xacro).

**Fix**: look at the controller_manager log. If it's missing
entirely, the hardware plugin probably threw during `on_init` /
`on_configure` and took the process down. Common causes:
- URDF expansion failed (run `xacro <file>` directly to see the error).
- `humanoid_devices_robstride` was rebuilt with an ABI-incompatible bump but
  the .so wasn't reinstalled. `colcon build --symlink-install --packages-select humanoid_devices_robstride`.

## Controllers fail to load/configure on a fresh `controller_manager`, and a reboot doesn't help

**Diagnosis**: a **second `controller_manager` on the same
`ROS_DOMAIN_ID`** — often on *another machine* on the LAN — is colliding
with yours over DDS. Hardware initializes fine ("Successful
initialization/activation of hardware"); only the controller spawners
fail ("Controller already loaded", "Failed to configure"), and rebooting
*your* robot changes nothing.

**Why**: every `controller_manager` defaults to the node name
`/controller_manager`. Two of them on one domain are two nodes sharing a
name and the same services, so spawner service calls hit the wrong CM or
get duplicate responses. When the other CM lives on a different machine,
rebooting yours can't fix it — the collider is still there. The default
domain (`0`) makes this easy to hit in a shared lab where several people
run bringups at once. Telltale sign: the *hardware* logs are all green
and only the controller-loading step misbehaves.

**Fix**: give the robot its own domain, and use the same value on every
machine that must see it (viz, teleop):

```toml
# workspace pixi.toml — every `pixi run` / `pixi shell` inherits this,
# including non-interactive SSH sessions (unlike a ~/.bashrc export).
[activation.env]
ROS_DOMAIN_ID = "5"
```

Then confirm exactly one CM is visible:

```bash
pixi run -- printenv ROS_DOMAIN_ID         # same value on every machine
ros2 node list | grep controller_manager   # must print exactly one
```

Coordinate the number with whoever owns domain allocation in your lab so
two robots don't collide, and never run two `controller_manager`
instances on one domain.

## Sim ignores the gamepad and controllers won't activate (stale `robot_state_publisher`)

**Diagnosis**: an orphaned `robot_state_publisher` from a *previous*
bringup is still running, and the new `controller_manager` latched its
**stale** `/robot_description` — so the wrong hardware plugin loaded
and no controller can claim its interfaces. The robot ignores the
gamepad, and even a hand `ros2 control switch_controllers` does nothing.

**Why**: when a bringup's parent process dies without a clean shutdown
— terminal closed, `kill -9` on the launcher, or the launch was
backgrounded and its shell then exited — the child nodes don't die with
it. On Linux they are re-parented to `systemd --user` and keep running.
The one that bites is `robot_state_publisher`: it publishes
`/robot_description` with **transient-local (latched)** QoS, so the old
URDF stays live on the bus even though no attached process is minding it.

Start a new bringup and its `controller_manager` subscribes to
`/robot_description`. If it latches the *stale* description first, it
loads the hardware component named there, then ignores the correct URDF
your new launch publishes ("already loaded"). With the wrong hardware
active, none of the new run's controllers can claim their interfaces, so
nothing activates and the gamepad / switch commands look dead. It bites
hardest when the previous run was a *different* robot variant than the
one you're launching now (e.g. an arms bringup still latched while you
start a biped one) — both write the same `/robot_description` topic.

Telltale lines in the new launch log:

```
[ros2_control_node] Failed to find joint 'left_shoulder_pitch' in mujoco model  # an arm joint, on a biped run
[resource_manager] Initialize hardware 'LiteHardware'   # you launched the biped -> expected 'LiteBipedHardware'
[controller_manager] ResourceManager has already loaded a urdf. Ignoring attempt to reload a robot description.
```

**Confirm it** — look for an orphan older than your current run (or more
than one copy), then check which hardware actually loaded:

```bash
pgrep -af robot_state_publisher   # a process much older than this run, or >1 copy
pgrep -af mujoco_sim
pgrep -af ros2_control_node
ros2 control list_hardware_components   # name / joints must match the robot you launched
```

If the component name or its joints don't belong to the robot you just
launched, you've latched a stale description.

**Fix**: kill the orphans, then relaunch:

```bash
pkill -f robot_state_publisher
pkill -f mujoco_sim            # add whatever else `pgrep` turned up
# then start the bringup again, e.g. pixi run deploy-sim-biped
```

**Prevent**: always stop a bringup with **Ctrl-C in its own terminal**
so `ros2 launch` propagates SIGINT and tears every child down cleanly
(verified: a clean Ctrl-C leaves no orphans). Don't close the terminal,
`kill -9` the launcher, or background the launch and then exit the shell.

This is distinct from *A gamepad button (or a switch) doesn't change the
controller* (there the button maps wrong but the controller loads fine)
and *Controllers fail to load/configure on a fresh `controller_manager`*
(there a second CM shares your domain): here the URDF itself is stale, so
`ros2 control list_hardware_components` names the wrong robot.

## DDS discovery fails between launches and `ros2 topic ...`

**Diagnosis**: `ROS_DOMAIN_ID` mismatch, or two `ros2 launch …`
instances running on the same domain on the same machine.

**Fix**: `echo $ROS_DOMAIN_ID` in both terminals. They must match (or
both unset = domain 0). If two launches are colliding, pick distinct
domains via `ROS_DOMAIN_ID=N` in each. If the symptom is specifically
*controllers* failing on an otherwise-healthy bringup, it's the
cross-machine CM collision above, not a plain discovery miss.

## ENOBUFS warnings *while a controller is active* (not boot)

**Diagnosis**: outbound CAN traffic exceeds the bus's drain rate over
sustained time. Usually a programming bug in a custom controller
(unbounded retries, mis-rate'd publish loop, etc).

**Fix**: check `tx_failed` counters in the SafetyStatus output. If a
controller is misbehaving, deactivate it and replace with
`zero_torque`. Otherwise raise `txqueuelen` as a workaround while you
diagnose.

## `pixi`, `curl`, or HTTPS `git clone` fail with TLS "certificate is not yet valid"

**Diagnosis**: the system clock is wrong — usually stuck in the **past**
— so otherwise-valid TLS certificates read as not-yet-valid.

**Why**: boards without a charged RTC (e.g. Jetson) reset their clock on
boot until NTP syncs. SSH doesn't check certificate dates, so `git@`
(SSH) clones keep working while **HTTPS** fails — which hides the real
cause and sends you chasing a network problem that isn't there.

**Fix**:

```bash
timedatectl                          # check "System clock synchronized"
sudo timedatectl set-ntp true        # enable NTP
sudo date -s '2026-06-27 15:00:00'   # or set by hand if the board is offline
```

## Edited a `humanoid_bringup_lite` script but the change has no effect

**Diagnosis**: the running copy under `install/` is stale — these
scripts are **installed as copies, not symlinked**.

**Why**: even with `colcon build --symlink-install`, plain scripts
installed via CMake `install(PROGRAMS ...)` (rather than ament_python
entry points) are **copied** into `install/.../share/`. Editing the
source under `src/` doesn't touch the installed copy that actually runs.

**Fix**: rebuild the owning package after editing such a script:

```bash
colcon build --symlink-install --packages-select humanoid_bringup_lite
```

## `pip install` "succeeds" but the package won't import inside `pixi run`

**Diagnosis**: `pip` installed into the user site (`~/.local/...`),
which the conda / RoboStack environment ignores.

**Why**: the RoboStack env often ships no `pip` module of its own, so a
bare `pip` falls back to a system/user `pip` that targets `~/.local`.
Conda-style environments don't put the user-site directory on
`sys.path`, so the import fails inside the env even though `pip` reported
success.

**Fix**: install Python deps *through pixi* so they land in the env:

```bash
pixi add --pypi viser     # PyPI-only packages (viser, yourdfpy, ...)
pixi add some-conda-pkg   # if it's available on conda-forge / robostack
```

## Prime eRob bringup takes ~70 s with repeated `0xA000` faults

**Diagnosis**: the eRob reach EtherCAT OP one at a time (~7 s each), and
`0xA000` (EtherCAT communication error) faults cycle until the domain is
complete.

**Why**: a slave reaches OP only after the master's DC drift compensation
converges, which is cycle-count bound. The ICube `ethercat_driver` `on_activate`
bring-up loop paced its `update()` at the 50 Hz control rate, so convergence
took ~7 s per slave; the faults are collateral (each joining slave briefly
starves the others' output watchdog).

**Fix**: a local patch to the ICube `ethercat_driver_ros2` (pinned by `bar.repos`)
runs the bring-up loop at 1 kHz, independent of `control_frequency`. Bringup drops
to ~13.6 s with zero faults, no steady-state change. See [Prime hybrid actuation](../concepts/prime_hybrid_actuation.md).

## Prime mode switch propagates slowly across the arm (one joint at a time)

**Diagnosis**: the right arm gets its new stiffness/damping seconds after the
left on a mode change.

**Why**: the eRob loop gains are written by acyclic SDO, and in OP each transfer
is cycle-gated (~120 ms). Writing 3 objects to 10 slaves in ring order is ~3.6 s,
right arm last.

**Fix**: keep `parallel_sdo` enabled (the default) on `erob_impedance_manager` —
concurrent per-slave writes pipeline through the IgH master to ~0.46 s, all
slaves within ~40 ms. See [Prime hybrid actuation](../concepts/prime_hybrid_actuation.md).

## Prime eRob faults `4616` immediately on enable

**Diagnosis**: CiA402 Fault state (statusword `4616`) right after activation; on
Prime this is the DC-sync / comms family.

**Why**: usually `control_frequency` does not equal the controller_manager
`update_rate`. SYNC0 is driven from the CM loop, so a mismatch means the
distributed clock never locks.

**Fix**: `lite_real.launch.py` derives `control_frequency` from the controllers YAML
`update_rate` so they cannot diverge; if you set it by hand, keep them equal
(50 Hz). Read the live error with `ethercat upload -pN 0x603F 0`.

## Cross-references

- **Hybrid actuation, PD conversion, eRob/Sito impedance**: [Prime hybrid actuation](../concepts/prime_hybrid_actuation.md)
- **Boot-time bringup checks**: [First real-hardware bringup → Common boot-time failures](../how_to/first_real_bringup.md#common-boot-time-failures)
- **Calibration drift**: [Calibrate the zero pose](../how_to/calibrate_zero_pose.md)
- **Bus / qdisc nitty-gritty**: [Diagnose ENOBUFS](../how_to/diagnose_enobufs.md)
- **Per-flag fault meaning + recovery**: [Recover from a fault](../how_to/recover_from_fault.md)
- **Controller switching (flat, via `joy_teleop` / `switch_controllers`)**: [Quick reference → Manual controller switching](./quick_reference.md#manual-controller-switching-no-fsm)
