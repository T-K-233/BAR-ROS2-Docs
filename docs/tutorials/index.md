---
id: index
title: Tutorials
sidebar_label: Overview
---

# Tutorials

Tutorials are **lessons**: you learn by following along, doing the same
thing every reader on this page does, and arriving at a working result.
They're the right place to look when you want to *develop competence*
in a part of the stack.

Reading order is loose — pick whichever subject is closest to what you
want to learn. Each assumes the [install](../getting_started/installation.md)
and [Lite 101](../getting_started/lite_101.md) lesson, nothing more.

| # | Tutorial | What you come away with |
|---|---|---|
| 1 | [Drive one Robstride end-to-end](./drive_one_robstride.md) | A single motor moving under our plugin, on bench hardware. Familiarity with the CAN bus, the MIT command surface, and the calibration math. |
| 2 | [MuJoCo + full FSM walkthrough](./mujoco_fsm_walk.md) | All five control modes exercised in sim, with the gamepad. Comfort with flat `joy_teleop` button switching and the standby pose. |
| 3 | [Run a tracking policy](./tracking_policy.md) | A trained tracking ONNX policy driving the arms in sim. Familiarity with the `humanoid_control_policy` runner, the self-describing ONNX metadata, and the LeRobot dataset path. |
| 4 | [Run the gravity-compensation demo](./run_gravity_compensation.md) | The Lite arms holding against gravity, driven by a host-side Python loop over DDS. Familiarity with the Tier-3 external-client path, the REMOTE mode, and `RemotePolicyController`. |
| 5 | [Build your own controller plugin](./build_your_own_controller.md) | A skeleton `humanoid_control/MyController` plugin loaded by the controller_manager. Familiarity with the `pluginlib` machinery and the `ControllerInterface` lifecycle. |

:::tip[Tutorial vs how-to]
A tutorial **teaches** — it gives you confidence and a mental model. A
[how-to guide](../how_to/index.md) **gets a specific thing done** — it's the
recipe you reach for once you already have that mental model.

If you find yourself reading a tutorial because you have a specific
problem to solve, the matching how-to is probably what you want.
:::
