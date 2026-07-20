---
id: index
title: Concepts
sidebar_label: Overview
---

# Concepts

Background reading. These pages discuss the *design* of `Humanoid Control` —
the architecture, the conventions, the trade-offs that decided which
abstractions live where. Read these when you want to understand the
project well enough to extend it (or argue with it).

If you're trying to get a specific job done, you probably want a
[how-to guide](../how_to/index.md) or the [reference](../reference/packages.md).
Concepts are for *understanding*, not for *doing*.

| Page | What it explains |
|---|---|
| [Architecture](./architecture.md) | The big picture: `ros2_control` as the spine, the in-process System 0 policy tier, the orthogonal axes (robot / hardware tier / task). |
| [Workspace & environment](./workspace_and_environment.md) | The three-tier code model (ROS / tooling / Tier-3 DDS), why pixi + RoboStack, and the config-repo + monorepo version-control split. |
| [Five-mode FSM](./five_mode_fsm.md) | The five control modes, what each is for, and the flat `joy_teleop` → `switch_controller` arbitration that replaced the old FSM. |
| [MIT command surface](./mit_command_surface.md) | Why every joint exposes 5 command interfaces, the `τ = K·err + D·erṙ + ff` convention, how it makes silicon / MuJoCo / mock interchangeable. |
| [Calibration math](./calibration_math.md) | The `direction` × `homing_offset` transform, where it lives (URDF + YAML), why it lives in the plugin and not the controller. |
| [Safety pipeline](./safety_pipeline.md) | `SafetyStatus` flags, who publishes them, native `fallback_controllers` on controller error, and why `/safety_status` is now operator telemetry. |
| [Frozen schemas](./frozen_schemas.md) | What "the schema is frozen once a policy depends on it" means in practice: joint order, message fields, command interfaces. |
