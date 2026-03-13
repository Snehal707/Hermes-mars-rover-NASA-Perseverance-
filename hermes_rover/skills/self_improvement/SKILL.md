---
name: self-improvement
description: Reuse successful learned rover behaviors in similar mission contexts and save new safe behaviors after successful non-trivial maneuvers
version: 1.0.0
tags: [learning, memory, navigation, safety, mars]
---

# Self Improvement Protocol

When handling a mission-like navigation, avoidance, or autonomous exploration task:

1. Read current context before planning any path or avoidance decision.
2. Consult learned behaviors with `rover_memory(action="get_behaviors")` when the current sensor context resembles a prior situation.
3. Prefer behaviors whose trigger matches the current coarse context and whose `success_count` is higher than `failure_count`.
4. Only reuse behaviors that stay within existing rover tools such as `drive_rover`, `navigate_to`, `read_sensors`, `rover_memory`, `check_hazards`, and `capture_camera_image`.
5. Never bypass safety rules. IMU tilt, LIDAR obstacle checks, hazard flags, and current telemetry always override learned behavior preferences.
6. Keep triggers coarse and reusable. Describe the situation with key sensor conditions, hazard or terrain cues, and mission intent, but do not include exact coordinates.
7. After a non-trivial maneuver or mission succeeds safely, save exactly one learned behavior with:
   `rover_memory(action="save_behavior", trigger="<short context>", behavior_action="<short tool sequence>", session_id="<active session>")`
8. The `behavior_action` must describe the real strategy in terms of existing tool calls so later missions can reuse it deterministically.
