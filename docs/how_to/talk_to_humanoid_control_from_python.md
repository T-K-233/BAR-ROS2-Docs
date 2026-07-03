---
title: Talk to Humanoid Control from Python
---

# Talk to Humanoid Control from Python

You have a host-side Python process — a gravity-comp runner, a VLA / manipulation
policy, a data tool — that needs to exchange messages with a running `Humanoid Control`
bringup, but you **don't** want `rclpy`, a colcon overlay, or
`--system-site-packages` in that environment. This is the **Tier-3** path: a
pure-pip process that joins the same DDS network the ROS nodes use.

You do not hand-write the message types. Two packages handle it:

- **`humanoid_control_msgs_dds`** — `cyclonedds` `IdlStruct` types **generated** from
  `humanoid_control_msgs/msg/*.msg` (see [Packages → `humanoid_control_msgs_dds`](../reference/packages.md#humanoid_control_msgs_dds)).
  Wire-compatible with ROS 2: it bakes in the rmw type-name mangling
  (`pkg::msg::dds_::Name_`) and the `rt/` topic prefix.
- **`lite_sdk2`** — a message-agnostic publisher/subscriber layer on top, with a
  per-type topic + QoS registry matching the bringup.

## 1. Add the dependency

`lite_sdk2` pulls in `humanoid_control_msgs_dds` and `cyclonedds`:

```toml
# pyproject.toml
dependencies = [
    "lite_sdk2 @ git+https://github.com/Berkeley-Humanoids/Lite-SDK2.git",
]
```

```bash
uv sync     # or: pip install "lite_sdk2 @ git+https://github.com/Berkeley-Humanoids/Lite-SDK2.git"
```

For local cross-repo development you can point either dependency at an in-tree
checkout via a `[tool.uv.sources]` path override in your **own** `pyproject.toml`.
Keep such overrides out of any package you *publish*: when a package is consumed
from git, uv rebases a relative path source onto that package's git origin, which
breaks resolution for downstream consumers.

## 2. Subscribe to robot state

```python
import lite_sdk2
from lite_sdk2 import JointState

lite_sdk2.initialize(domain_id=0, network_interface="enp2s0")   # match ROS_DOMAIN_ID

sub = lite_sdk2.subscriber(JointState)     # topic + QoS resolved from the registry
sub.initialize()
state = sub.read(timeout=0.5)              # one sample, or None on timeout
if state is not None:
    print(state.name, state.position)
```

## 3. Publish a command

`RemotePolicyController` consumes `MITCommand` (in the **REMOTE** mode of the
[five-mode FSM](../concepts/five_mode_fsm.md)). Drive the FSM into REMOTE first
(gamepad, or [switch controllers manually](./switch_controllers_manually.md)).

```python
from lite_sdk2 import MITCommand, zero_mit_command

pub = lite_sdk2.publisher(MITCommand)
pub.initialize()
pub.wait_for_reader(timeout=2.0)           # optional, not realtime-safe

# A safe "park" command: zero stiffness, light damping, for the live joints.
pub.write(zero_mit_command(state.name, damping=2.0))
```

`write()` is realtime-safe (fire-and-forget). Build a full command with the
[five MIT interfaces](../concepts/mit_command_surface.md) directly on `MITCommand`.

## Topic & QoS defaults

`lite_sdk2` resolves these from its registry; override per call with
`topic=` / `qos=`.

| Type | ROS topic | QoS |
|---|---|---|
| `MITCommand` | `/remote_policy_controller/command` | reliable, depth 4 |
| `JointState` | `/lite/joint_states` | reliable, depth 10 |
| `ControlMode` | `/control_mode` | reliable |
| `SafetyStatus` | `/safety_status` | reliable |
| `StandbyState` | `/standby_controller_a/state` (one per pose; `_b` for Pose B) | transient-local (latched) |

QoS reliability and durability **must** match the bringup for DDS to pair a
writer with a reader — the registry already encodes the matching values.

## CLIs

```bash
lite-sdk2-monitor enp2s0 joint_states     # print decoded JointState traffic
lite-sdk2-control enp2s0 damping          # stream a damping command (discovers joints from /joint_states)
lite-sdk2-control enp2s0 disable          # zero-torque burst, then exit
```

## Changing a message

Messages live in `Humanoid Control`, not in the SDK. Edit `humanoid_control_msgs/msg/*.msg`, run
`pixi run gen-dds` to regenerate `humanoid_control_msgs_dds`, and the new/changed type flows
through `lite_sdk2` automatically — there is no schema to mirror by hand. This is
a [frozen-schema change](../concepts/frozen_schemas.md#how-to-change-a-frozen-schema);
follow the full drill if a trained policy depends on it.

## Gotchas

- **`domain_id` must match `ROS_DOMAIN_ID`** on the bringup (default 0).
- **Pick the right NIC** with `network_interface=` — multicast discovery binds to it.
- **No `rclpy`.** `cyclonedds-python` interoperates with `rmw_cyclonedds_cpp` or
  `rmw_fastrtps_cpp` on the bringup — both are RTPS-over-UDP with CDR. No
  `RMW_IMPLEMENTATION` override needed.
