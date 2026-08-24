# Lite 101

A 20-minute hands-on lesson. You'll go from "URDF loaded in RViz" to "the
full controller stack running in MuJoCo, with a controller switch under
your fingers". By the end you'll recognise the four moving pieces of the
project — the URDF, the controller_manager, the mode controllers, and
the simulation backend — and be ready to read the rest of the docs with
that mental model in place.

:::tip[This is a tutorial, not a how-to]
The aim here is **learning by doing**, not "production realism". For
calibrating a real robot, recovering from a fault, or wiring a gamepad,
look in [How-to guides](../how_to/index.md) once those land. For the
why-behind-the-what, [Concepts](../concepts/index.md).
:::

Prerequisites: a built workspace, from the [previous page](./installation.md).
Every command on this page runs inside `pixi shell` (one-time per
terminal, sources ROS 2 Jazzy + the workspace overlay):

```sh
cd humanoid_control_ws && pixi shell
```

Stay in that shell for the rest of the lesson. If you ever want
shorter shortcuts (e.g. `pixi run sim`) the equivalent
tasks live in [How-to → Workspace shortcuts with
pixi](../how_to/use_pixi_tasks.md); the canonical `ros2 launch`
form is what's shown below.

## Step 1 — Visualize the URDF

The simplest possible launch: `robot_state_publisher` + a
`joint_state_publisher_gui` + RViz. No physics, no `ros2_control` — just
the kinematic chain.

```sh
ros2 launch humanoid_bringup_lite lite_view.launch.py
```

What you'll see:

- **RViz** opens with the chest at world origin and the arms hanging at
  zero pose.
- A **slider panel** (jsp_gui) appears with one slider per actuated joint.
- Dragging a slider rotates the corresponding link in RViz.

:::tip["What is xacro doing?"]
The `.xacro` file is a Jinja-ish macro language for URDFs. The top-level
`lite.urdf.xacro` includes `lite.ros2_control.xacro`, which selects the
`<plugin>` based on the `sim_mujoco` / `use_mock_hardware` args. For RViz
visualization we force `use_mock_hardware:=true` so the `<ros2_control>`
block is harmless (`mock_components/GenericSystem`, which never gets
loaded because RViz doesn't spawn `controller_manager`).
:::

Close the launch (`Ctrl+C` in the terminal) before moving on.

## Step 2 — Bring up MuJoCo

Now the full control plane against MuJoCo physics: `controller_manager`
hosted inside `mujoco_sim`, all five mode controllers loaded, with
`zero_torque_controller` active as the safe default. Switching between
modes is flat — the stock `joy_teleop` node maps gamepad buttons
directly to `controller_manager` switches (there is no FSM
orchestrator); with no gamepad here, we'll make one such switch by hand
below. Nothing on the CAN bus — the
`MujocoSystem` hardware plugin applies the same MIT-mode torque
`τ = K·(q_cmd − q) + D·(q̇_cmd − q̇) + effort` to `qfrc_applied` that
the Robstride firmware computes on silicon.

```sh
ros2 launch humanoid_bringup_lite lite_mujoco.launch.py
```

A **MuJoCo viewer window** opens with the Lite humanoid at zero pose.
The single `mujoco_sim` process hosts MuJoCo physics, the
`MujocoRos2ControlPlugin` (loaded as a pluginlib physics plugin), the
`controller_manager` inside that, and the `MujocoSystem` hardware
interface inside that. From the controller's point of view nothing
distinguishes this from real hardware — same 5 command interfaces, same
3 state interfaces.

![mujoco_sim process](/img/diagrams/getting_started__lite_101__02_mujoco_internals.svg)

Wait ~2 seconds, then in a **second terminal** (also inside `pixi shell`):

```sh
ros2 control list_controllers
```

Expected output (give or take):

```
joint_state_broadcaster   joint_state_broadcaster/JointStateBroadcaster   active
zero_torque_controller    humanoid_control/ZeroTorqueController                        active
damping_controller        humanoid_control/DampingController                           inactive
standby_controller_a      humanoid_control/StandbyController                           inactive
standby_controller_b      humanoid_control/StandbyController                           inactive
standby_controller_y      humanoid_control/StandbyController                           inactive
rl_policy_controller      humanoid_control/RLPolicyController                          inactive
remote_policy_controller  humanoid_control/RemotePolicyController                      inactive
```

### What just happened

![MuJoCo bringup spawn sequence](/img/diagrams/getting_started__lite_101__01_mujoco_spawn.svg)

`zero_torque_controller` is active as the **safe startup default**: it
claims all 5 command interfaces on every joint and writes 0 to all of
them every tick. From an operator's perspective the robot is "alive but
inert".

The five other controllers are **loaded but inactive**. Loading them
runs their `on_configure` (params parsed, publishers/subscribers created)
without claiming the command interfaces. They sit ready to be activated
in a single service call.

### Watch the topics

```sh
ros2 topic list | grep -E "joint_states|standby|safety"
# /lite/joint_states
# /safety_status
# /standby_controller_a/state
```

`joint_state_broadcaster` is remapped at bringup so that it publishes on
`/lite/joint_states` (the owner-prefixed topic) rather than the global
`/joint_states`. The controller_manager's update rate is 200 Hz in
MuJoCo, 50 Hz on real hardware:

```sh
ros2 topic hz /lite/joint_states
# average rate: 200.000
```

There is no `/control_mode` topic — the active mode isn't published;
it's simply whichever controller `ros2 control list_controllers` reports
as `active` (Step 2 above). `/safety_status` is published as telemetry:
an operator (or a monitor) watches it, but it does **not** switch modes
for you — a fault is caught by the controllers' native fallback instead.

:::tip["See it move"]
Two interchangeable live visualizers ride on `/lite/joint_states` +
`/robot_description`, both shipped by `humanoid_bringup_lite`. On the
tethered deployment they live on the **operator workstation** (host
side of the tether), spawned by `viz.launch.py`:

```sh
ros2 launch humanoid_bringup_lite viz.launch.py                  # viser, http://localhost:8080
ros2 launch humanoid_bringup_lite viz.launch.py viewer:=rerun    # native rerun window
```

For a single-machine MuJoCo run, the standalone shortcuts work too —
they auto-discover `/robot_description` and the joint-state topic on
the local domain:

```sh
ros2 run humanoid_bringup_lite viser_viz
ros2 run humanoid_bringup_lite rerun_viz
```

Visualiser dependencies (`rerun-sdk`, `viser`, `yourdfpy`, `scipy`)
ship in the pixi env. See
[How-to → Live visualization](../how_to/live_viz.md) and
[Concepts → Architecture → Deployment topology](../concepts/architecture.md#deployment-topology).
:::

## Step 3 — Switch modes by hand

The whole project switches modes by switching controllers — flat and
direct, with no ordering rules. Pressing the gamepad **X** button makes
`joy_teleop` call the controller_manager to activate `damping_controller`
and deactivate the rest. This lesson has no gamepad, so we make that
same call by hand:

```sh
ros2 control switch_controllers \
    --activate damping_controller \
    --deactivate zero_torque_controller
```

Verify:

```sh
ros2 control list_controllers
# damping_controller        humanoid_control/DampingController                           active
# zero_torque_controller    humanoid_control/ZeroTorqueController                        inactive
```

:::tip[Why DAMPING is the "compliant fail-safe"]
With stiffness `K = 0` there's no position-restoring force. With damping
`D` nonzero the joint resists velocity. The result: the robot is **soft
under gravity** (push the arm and it moves) but **damped** (it doesn't
oscillate). This is the state you transition into before powering down,
before swapping a tool, or that the controllers' native fault fallback
drops into. See [Concepts → Five control modes](../concepts/five_mode_fsm.md).
:::

If gravity is on (it is by default in our MJCF) and you switched to
DAMPING after a few seconds in ZERO_TORQUE, the arms in the MuJoCo
viewer should now **sag and settle** rather than freely flopping — the
damping resists fall velocity but the zero stiffness can't hold them
up. That contrast between the two modes is the lesson of this step.

## Step 4 — Switch back, then exit

Always end a session in a known safe state. Switch back to ZERO_TORQUE,
which makes the motors fully compliant again:

```sh
ros2 control switch_controllers \
    --activate zero_torque_controller \
    --deactivate damping_controller
```

Then `Ctrl+C` the launch terminal. The plugin's `on_deactivate` runs,
sending Disable to every joint (no-op in MuJoCo but matters on silicon),
and `mujoco_sim` shuts down cleanly.

## What you just saw

Four moving pieces, all worth recognising for the rest of the docs:

| Piece | What it does |
|---|---|
| **URDF** (`lite_description`) | Kinematic + dynamic description. Same file across mock / sim / real — the `<ros2_control>` `<plugin>` is the only difference. |
| **`controller_manager`** | Hosts the hardware plugin + every controller. The "tick loop" of the system. Update rate 50 Hz here. |
| **Mode controllers** (`humanoid_controllers`) | Five plugins, one active at a time. `zero_torque` (safe default), `damping` (compliant fail-safe), `standby` (interpolate to a pose), `rl_policy` (in-process ONNX — the System 0 learned-policy tier), `remote_policy` (System 1/2 external-command ingress for non-real-time `MITCommand` sources). |
| **MuJoCo / Robstride** (the simulation / real backend) | Where the MIT torque actually gets applied. Same five command interfaces in both. |

## Next

Where to go from here, depending on what you want:

- **I want to make the arm move on real hardware.**
  → [How-to → First real-hardware bringup](../how_to/first_real_bringup.md).
- **I want a hands-on look at all five modes, with the actual gamepad.**
  → [Tutorials → MuJoCo + FSM walkthrough](../tutorials/mujoco_fsm_walk.md).
- **I want to run a trained policy.**
  → [Tutorials → Run a tracking policy](../tutorials/tracking_policy.md).
- **I want one page that lists every command, every topic, every gamepad button.**
  → [Reference → Quick reference](../reference/quick_reference.md).
- **I want to understand the design rationale.**
  → [Concepts → Architecture](../concepts/architecture.md).
