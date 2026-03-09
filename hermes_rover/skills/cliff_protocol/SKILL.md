---
name: cliff-protocol
description: Emergency protocol when cliff or drop-off is detected
version: 1.0.0
tags: [cliff, emergency, safety, mars]
---

# Cliff Emergency Protocol

When LIDAR indicates cliff or sudden drop-off ahead:

1. **Emergency stop** — drive_rover with linear=0, angular=0
2. Reverse 3 meters (drive_rover backward)
3. Mark cliff location in memory with coordinates (from odometry)
4. Scan for alternative route — 360° LIDAR to find safe direction
5. Navigate around cliff (navigate_to to waypoint that avoids hazard)
6. Avoid this area in future sessions — log hazard location to memory
