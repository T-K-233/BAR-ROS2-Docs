---
title: Run the gravity-compensation demo
sidebar_position: 4
---

# Tutorial: Run the gravity-compensation demo

Drive the Lite arms from a **host-side Python process** — no `rclpy`, no
colcon overlay, no `--system-site-packages`. You'll bring up the stack
(MuJoCo or real), walk the FSM into **REMOTE**, and run an external
gravity-compensation loop that reads joint states and publishes
`MITCommand` back over raw DDS. By the end you'll understand the
**Tier-3 external-client path**, the REMOTE mode of the five-mode FSM,
and the difference between the torque-mode and PD-mode gravity loops.

This is the worked, end-to-end companion to
[How-to → Talk to Humanoid Control from Python](../how_to/talk_to_humanoid_control_from_python.md):
that page is the recipe, this is the lesson.

## Time + materials

- 20 minutes
- A working workspace build (the bringup side)
- The [`Lite-Gravity-Compensation`](https://github.com/Berkeley-Humanoids/Lite-Gravity-Compensation)
  demo, checked out **anywhere outside `humanoid_control_ws`** (it's a standalone
  Tier-3 project with its own `uv` environment — it only needs to reach
  the robot's DDS bus, not the colcon workspace)
- [`uv`](https://docs.astral.sh/uv/) on PATH for the demo's own env
- No real hardware required — the whole lesson runs in MuJoCo

## The mental model

The gravity-comp runner is **not** a controller and **not** a ROS node.
It's an ordinary Python process that joins the same DDS network the
bringup uses. The in-process `humanoid_control::RemotePolicyController` is the only
thing that touches the command interfaces; the external loop just feeds
it `MITCommand`s:

```
   host-side process (pure pip, no rclpy)        Humanoid Control bringup (System 0, RT)
   ┌───────────────────────────────┐            ┌──────────────────────────────┐
   │ run_ros2_torque.py            │            │ joint_state_broadcaster       │
   │   each tick @ COMMAND_HZ:     │  rt/lite/  │   publishes /lite/joint_states│
   │   1. drain /lite/joint_states │◀───joint_  │                               │
   │      → 14-joint snapshot      │   states   │                               │
   │   2. mirror into MuJoCo;      │            │                               │
   │      mj_forward + subtree     │            │                               │
   │      COM → gravity torques    │            │ RemotePolicyController        │
   │      (model only, no stepping)│  rt/remote_│   (REMOTE mode)               │
   │   3. build MITCommand         │  policy_   │   reads ~/command, writes the │
   │   4. pub /remote_policy_       │──controller│   5 MIT command interfaces    │
   │      controller/command       │  /command ▶│   per joint                   │
   └───────────────────────────────┘            └───────────────┬──────────────┘
                                                                 ▼
                                                  MujocoSystem (sim)  or
                                                  RobstrideSystem (real)
                                                  applies τ = K·err + D·errṙ + ff
```

:::note[Two MuJoCos, two jobs]
In the sim bringup, `MujocoSystem` **simulates physics** and applies the
torques. The demo's *own* MuJoCo is a **dynamics model only** — it never
steps; it just computes gravity-cancelling generalized forces from the
live joint snapshot. They are independent.
:::

## Step 1 — Install the demo

The demo has its own `uv` environment, fully separate from the pixi /
colcon workspace. From the demo checkout:

```bash
cd Lite-Gravity-Compensation
uv sync
```

`uv sync` resolves the two host-side packages straight from their git
repos — [`lite_sdk2`](../reference/packages.md#humanoid_control_msgs_dds) (the
publisher/subscriber + QoS registry) and `humanoid_control_msgs_dds` (the
ROS-wire-compatible CycloneDDS message types, pulled in transitively).
Nothing here links against `rclpy`.

:::info[Why no `rclpy`?]
ROS 2 messages are just CDR-serialized DDS types. `lite_sdk2` reproduces
the three rmw conventions — the `rt/` topic prefix, the
`pkg::msg::dds_::Name_` type-name mangling, and RELIABLE/KEEP_LAST QoS —
so `cyclonedds-python` pairs directly with `rmw_cyclonedds_cpp` *or*
`rmw_fastrtps_cpp` on the bringup. See
[How-to → Talk to Humanoid Control from Python](../how_to/talk_to_humanoid_control_from_python.md).
:::

## Step 2 — Bring up the stack

In the **bringup** terminal (inside `pixi shell`), start MuJoCo:

```bash
cd humanoid_control_ws && pixi shell
ros2 launch humanoid_bringup_lite mujoco.launch.py
```

Wait for `zero_torque_controller` to come active. (For real hardware,
use `real.launch.py` instead — everything downstream is identical.)

## Step 3 — Walk the FSM into REMOTE

`RemotePolicyController` only accepts commands in the **REMOTE** mode,
and the FSM only enters REMOTE from a *finished* STANDBY. Drive the
transitions through `mode_manager`'s trigger services (in a second
terminal, inside `pixi shell`):

```bash
ros2 service call /humanoid_control/mode/damp std_srvs/srv/Trigger    # → DAMPING (gamepad: X)
ros2 service call /humanoid_control/mode/load_a std_srvs/srv/Trigger  # → STANDBY, Pose A (gamepad: L1+A)

# Wait until the standby ramp reports finished:
ros2 topic echo /standby_controller_a/state
# ... is_finished: true

ros2 service call /humanoid_control/mode/start_remote std_srvs/srv/Trigger   # → REMOTE (gamepad: R1+B)
```

:::caution[`start_remote` is R1+B, not R1+A]
**R1+A** starts LOCOMOTION (the in-process `rl_policy_controller`);
**R1+B** starts REMOTE (`remote_policy_controller`). Use the `B`
combo / the `start_remote` service for this demo.
:::

Confirm REMOTE is active before running the loop:

```bash
ros2 topic echo --once /control_mode
# mode: 4   (REMOTE)
# controller_name: remote_policy_controller
```

## Step 4 — Run the gravity-comp loop (torque mode)

Back in the **demo** terminal (the `uv` env, not pixi). Match
`ROS_DOMAIN_ID` to the bringup (both default to `0`):

```bash
cd Lite-Gravity-Compensation
source .venv/bin/activate
python run_ros2_torque.py
```

You should see the banner and, once the first full joint snapshot
arrives, a periodic torque readout:

```
DDS domain=0  mode=torque  joints=14  rate=... Hz  model=...
First complete /lite/joint_states received.
[hh:mm:ss] torque mean=0.412  max=1.083
```

In the MuJoCo viewer the arms now **hold against gravity** — nudge a
link and it stays where you leave it instead of falling. Torque mode
sends `effort = clipped gravity torque`, `K=0`, `D=TORQUE_DAMPING`, so
the actuator's MIT formula reduces to a gravity-cancelling feedforward
plus a passive viscous brake.

## Step 5 — Try PD mode

Stop the torque loop (Ctrl-C — see [Safe stop](#step-6--safe-stop)) and
run the PD variant instead:

```bash
python run_ros2_pd.py
```

PD mode encodes the same gravity term as a **position offset**
(`position = q + gravity/Kp`) with non-zero stiffness/damping
(`K=PD_POSITION_KP`, `D=PD_VELOCITY_KD`). The arm feels stiffer and
self-centering rather than free-floating. Both publish in
`LITE_ARM_JOINTS` order (the `arm_joints` list in
`humanoid_bringup_lite/config/lite_hardware.yaml`); `RemotePolicyController`
rejects a joint-order mismatch.

:::tip[No bringup, no robot]
`python run_mujoco.py` opens the demo's MuJoCo model in a passive viewer
with the same gravity compensation applied in-process — no DDS, no FSM.
Handy for sanity-checking the model alone.
:::

## Step 6 — Safe stop

`Ctrl-C` publishes **one** final passive command (`K=0`,
`D=TORQUE_DAMPING`, `effort=0`) — the actuator coasts under damping —
then the process exits. That is *not* a real stop: the controller stays
in REMOTE, and `RemotePolicyController`'s stale-command fallback (~100 ms
of silence) treats the now-quiet topic as a fault and falls back to
damping.

For a deliberate stop, drive the FSM back down first:

```bash
ros2 service call /humanoid_control/mode/damp std_srvs/srv/Trigger    # gamepad: X
```

Then Ctrl-C the runner, then the bringup launch.

## What you came away with

| Skill | Page where it's documented in detail |
|---|---|
| The Tier-3 external-client (no-`rclpy`) DDS path | [How-to → Talk to Humanoid Control from Python](../how_to/talk_to_humanoid_control_from_python.md) |
| `lite_sdk2` / `humanoid_control_msgs_dds` topic + QoS registry | [Reference → Packages](../reference/packages.md#humanoid_control_msgs_dds) |
| The REMOTE mode + `start_remote` transition | [Concepts → Five-mode FSM](../concepts/five_mode_fsm.md) |
| `RemotePolicyController` and the MIT command write | [Reference → Controllers](../reference/controllers.md) |
| The five MIT command interfaces (torque vs PD encoding) | [Concepts → MIT command surface](../concepts/mit_command_surface.md) |

## Next

- [Tutorials → Run a tracking policy](./tracking_policy.md) — the
  *in-process* counterpart: a policy that runs inside the RT cycle
  instead of over DDS.
- [Concepts → MIT command surface](../concepts/mit_command_surface.md) —
  why `position` / `velocity` / `effort` / `stiffness` / `damping` is the
  whole command surface, and how torque- and PD-mode gravity comp map
  onto it.
- [How-to → Switch controllers manually](../how_to/switch_controllers_manually.md)
  — the lower-level path if you'd rather bypass `mode_manager`.
