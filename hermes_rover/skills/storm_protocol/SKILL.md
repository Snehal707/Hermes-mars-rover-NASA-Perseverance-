---
name: storm-protocol
description: Emergency protocol when dust storm is detected
version: 1.0.0
tags: [storm, emergency, safety, mars]
---

# Dust Storm Emergency Protocol

When a dust storm is detected or check_hazards returns storm hazard:

1. **Immediate stop** — drive_rover with linear=0, angular=0
2. Log current position to memory (read sensors, record coordinates)
3. Alert operator via Telegram — send "STORM DETECTED. Parked at [coords]. Entering safe mode."
4. Enter monitoring mode — check every 5 minutes (read_sensors, check_hazards)
5. When visibility improves (storm passes): send "STORM CLEARED" message
6. Run diagnostics — full sensor check before resuming
7. Resume previous mission from saved position
