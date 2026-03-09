---
name: obstacle-avoidance
description: Navigate around obstacles detected by LIDAR
version: 1.0.0
tags: [obstacle, navigation, safety, mars]
---

# Obstacle Avoidance Protocol

When an obstacle is detected:

1. **STOP** immediately (drive_rover with linear=0, angular=0)
2. Read sensors — full 360° LIDAR scan (read_sensors with lidar)
3. Find clearest direction (longest clear range, minimum 10 m)
4. Turn toward that direction (drive_rover with angular_speed)
5. Verify new heading is clear with forward LIDAR check
6. Resume at reduced speed (linear 0.3 m/s)
7. After 10 m clearance past obstacle, resume normal speed

If no direction has >5 m clearance: REVERSE 3 m and re-scan.
