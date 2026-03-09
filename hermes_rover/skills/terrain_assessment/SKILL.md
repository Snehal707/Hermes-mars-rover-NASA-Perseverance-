---
name: terrain-assessment
description: Classify terrain from IMU tilt and adjust speed accordingly
version: 1.0.0
tags: [terrain, safety, navigation, mars]
---

# Terrain Assessment Protocol

1. Read IMU for tilt angles (read_sensors with imu; or check bridge GET / for orientation roll, pitch)
2. Classify terrain:
   - **Flat:** roll and pitch < 0.2 rad — normal max speed (1.0 m/s)
   - **Mild slope:** 0.2–0.35 rad — reduce to 0.5 m/s
   - **Steep:** 0.35–0.52 rad — reduce to 0.2 m/s, consider reversing
   - **Dangerous:** > 0.52 rad — STOP, reverse to safer terrain
3. Adjust max speed based on classification (use drive_rover with clamped linear_speed)
4. Log terrain type and location to memory for future sessions
