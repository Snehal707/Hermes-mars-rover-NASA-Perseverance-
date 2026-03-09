# How to Record the HERMES Mars Rover Hackathon Demo

## Headless Demo

Run `scripts/demo_session.py`, then screen record the terminal, dashboard (localhost:3000), and Telegram. No Gazebo GUI required.

```bash
./scripts/demo_session.py
```

## Visual Demo (Full Simulation)

1. Rent a GPU VPS (e.g., Lambda, RunPod, Hetzner CCX with GPU)
2. Install Gazebo with GUI, ROS 2, and the bridge
3. Run the full sim (Gazebo window + bridge + API)
4. Screen record: Gazebo window + dashboard + Telegram
5. Show the rover driving in the 3D view

## Recommended Demo Flow

1. **Start simulation** — Gazebo + bridge + API
2. **Rover driving** — Send "move forward 5 meters"
3. **Trigger hazard** — Show tilt or cliff detection; skill activation
4. **Memory saving** — Show session logs, hazard map
5. **Telegram control** — Send command from phone
6. **Dashboard** — Live telemetry, map, sensors
7. **Skill files** — Show SKILL.md (obstacle-avoidance, storm-protocol)
8. **Generate report** — Run `generate_report` tool or session summary

## Video Length

3–5 minutes recommended.

## Tools

Use **OBS Studio** (or similar) for screen recording.
