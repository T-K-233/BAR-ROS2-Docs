---
id: index
title: How-to guides
sidebar_label: Overview
---

# How-to guides

Recipes for specific problems. Each page assumes you have a working
install, have done the [Lite 101](../getting_started/lite_101.md) lesson,
and now have a concrete task in mind. How-tos skip the pedagogy that
[tutorials](../tutorials/index.md) include — they go straight to the steps.

## Bring-up & operations

| Guide | Use it when |
|---|---|
| [First real-hardware bringup](./first_real_bringup.md) | You have the physical Lite robot on the bench and a workspace built. You want `/lite/joint_states` to flow and `zero_torque_controller` active. |
| [Calibrate the zero pose](./calibrate_zero_pose.md) | The URDF "joint zero" doesn't match where the robot's encoders read zero. You want to regenerate `humanoid_bringup_lite/config/calibration.yaml`. |
| [Probe actuators on a CAN bus](./probe_can_bus.md) | You suspect a wiring issue, a missing motor, or just want to scan all IDs on a bus before bringup. |
| [Switch controllers without the FSM](./switch_controllers_manually.md) | The gamepad isn't in the loop. You want to call `switch_controller` directly to put the robot in DAMPING / STANDBY / REMOTE. |

## Manual control & debug

| Guide | Use it when |
|---|---|
| [Drive a single joint with mit_slider_gui](./mit_slider_gui.md) | You want to inject a position/velocity/effort/K/D combination by hand and see the actuator follow. Good for sanity-checking a freshly calibrated joint. |
| [Live-visualize the robot (rerun / viser)](./live_viz.md) | You want the live kinematic chain on screen while the robot runs — for tuning, demos, or watching a policy from another machine. |
| [Record experiments with rosbag (MCAP)](./record_experiments.md) | You want a replayable trace — joints, controller switches, safety status, policy I/O — for offline analysis, regression baselines, or Foxglove Studio. |

## Diagnosis & recovery

| Guide | Use it when |
|---|---|
| [Diagnose ENOBUFS / TX drops](./diagnose_enobufs.md) | The plugin spams `Network is down` or you see `tx_failed` counters climb. Usually motor power is off or `txqueuelen` is too small. |
| [Recover from a fault](./recover_from_fault.md) | `/safety_status` reported `BUS_OFF`, `RX_TIMEOUT`, or `TEMPERATURE_LIMIT`, or a control-mode controller errored into its `damping` fallback. |

## Extension

| Guide | Use it when |
|---|---|
| [Run and extend an in-process policy](./promote_python_to_cpp.md) | You have a trained `.onnx` and want to ship it via the launch-time `prepare` step into the in-process C++ `RLPolicyController` (System 0) — or you need to add a new observation term or task. |
| [Talk to Humanoid Control from Python](./talk_to_humanoid_control_from_python.md) | You want a host-side Python process (gravity-comp, VLA, data tool) to publish/subscribe `humanoid_control_msgs` over DDS with no `rclpy` — via `lite_sdk2` + the generated `humanoid_control_msgs_dds` types. |
| [Add a new joint to the URDF](./add_new_joint.md) | A new actuator goes on the robot. You need to wire it into the URDF, controllers YAML, and `calibration.yaml`. |
