# HERMES Mars Rover — AI-Powered Mars Exploration Simulation

[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org)
[![ROS 2](https://img.shields.io/badge/ROS%202-Humble%2FJazzy-green.svg)](https://www.ros.org)
[![Gazebo](https://img.shields.io/badge/Gazebo-Harmonic%2FJetty-orange.svg)](https://gazebosim.org)
[![Hermes Agent](https://img.shields.io/badge/Hermes%20Agent-Nous%20Research-red.svg)](https://github.com/NousResearch/hermes-agent)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

AI-powered Mars rover simulation using **Hermes Agent** (Nous Research) as the brain. Control a Perseverance-class rover in Gazebo via natural language, Telegram, web dashboard, or Apple Watch. Features autonomous navigation, hazard detection, skill learning, and persistent memory.

---

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│                    CONTROL LAYER                         │
│  ┌─────────┐  ┌──────────┐  ┌───────────┐  ┌─────────┐ │
│  │Telegram │  │Apple Watch│  │ Web Dash  │  │ Hermes  │ │
│  │  Bot    │  │  / Siri   │  │ (Next.js) │  │  CLI    │ │
│  └────┬────┘  └─────┬─────┘  └─────┬─────┘  └────┬────┘ │
│       │             │              │              │      │
│       └─────────────┴──────┬───────┴──────────────┘      │
│                            │                             │
│                    ┌───────▼────────┐                    │
│                    │  COMMAND API   │                    │
│                    │  (FastAPI)     │                    │
│                    └───────┬────────┘                    │
└────────────────────────────┼─────────────────────────────┘
                             │
┌────────────────────────────┼─────────────────────────────┐
│                    AI LAYER│                              │
│                    ┌───────▼────────┐                    │
│                    │ HERMES AGENT   │                    │
│                    │ (Nous Hermes)  │                    │
│                    │ • Tool Calling │                    │
│                    │ • Memory       │                    │
│                    │ • Skills       │                    │
│                    └───────┬────────┘                    │
│                            │                             │
│              ┌─────────────┼─────────────┐               │
│        ┌─────▼─────┐ ┌────▼─────┐ ┌─────▼─────┐        │
│        │  Skill DB │ │ Memory   │ │ Session   │        │
│        │ (SKILL.md)│ │ (SQLite) │ │ Logs (DB) │        │
│        └───────────┘ └──────────┘ └───────────┘        │
└────────────────────────────┼─────────────────────────────┘
                             │
┌────────────────────────────┼─────────────────────────────┐
│                 SIMULATION LAYER                         │
│                    ┌───────▼────────┐                    │
│                    │  SENSOR BRIDGE │                    │
│                    │  (port 8765)   │                    │
│                    └───────┬────────┘                    │
│                    ┌───────▼────────┐                    │
│                    │  GAZEBO SIM    │                    │
│                    │ • Mars World   │                    │
│                    │ • Perseverance │                    │
│                    │ • Sensors      │                    │
│                    └────────────────┘                    │
└──────────────────────────────────────────────────────────┘
```

---

## Quick Start

1. **Clone** this repository
2. **Install dependencies**: `make setup` (or `pip install -r requirements.txt` if present; install Gazebo, ROS 2 per build plan)
3. **Configure Hermes**: `hermes setup` — select OpenRouter, add `OPENROUTER_API_KEY`
4. **Configure `.env`**: Copy `.env.example` to `.env` and fill API keys (Telegram, etc.)
5. **Run**: `./scripts/start_all.sh` or `make all`
6. **Dashboard env (optional)**: In `dashboard/`, copy `.env.local.example` to `.env.local` and set `NEXT_PUBLIC_API_BASE_URL` if API is on another host/IP.

Then open the dashboard at `http://localhost:3000` (`make dashboard` in a separate terminal) and API docs at `http://localhost:8000/docs`.

---

## GPU VPS Visualization

If you want to keep the rover agent headless but still see the rover move on a GPU VPS, use the remote visualization path:

- `./scripts/start_all_vps.sh` to run the full stack with Gazebo headless rendering and the websocket visualization server
- `./scripts/start_sim_vps.sh` to launch only the Gazebo simulation for remote viewing
- `docs/GPU_VPS_DEPLOYMENT.md` for the VPS install, SSH tunnel, and browser connection flow

This keeps the Hermes control loop unchanged while exposing Gazebo visualization in a browser.

---

## Features

- **Autonomous navigation** — Natural language commands via Hermes Agent
- **Hazard detection** — Cliffs, obstacles, tilt; storm protocol
- **Skill learning** — SKILL.md files for obstacle-avoidance, storm-protocol, terrain assessment
- **Persistent memory** — SQLite for sessions, hazards, learned behaviors
- **Automatic learned-behavior reuse** — successful rover strategies are logged and reused in later similar missions
- **Telegram control** — Text and voice commands via bot
- **Web dashboard** — Live telemetry, map, sensors, command input
- **Apple Watch / Siri** — Shortcuts for status, move, photo
- **Session reports** — Cron jobs for periodic reports via Telegram

---

## Project Structure

```
hermes-mars-rover/
├── simulation/       # Gazebo worlds, models
├── hermes_rover/     # Tools, skills, memory
├── bridge/           # Sensor bridge (port 8765)
├── api/              # FastAPI (port 8000)
├── telegram_bot/     # Custom bot (optional)
├── dashboard/        # Next.js web UI
├── apple_watch/      # Siri / Shortcuts setup
├── scripts/          # start_all.sh, start_sim.sh, etc.
└── tests/            # test_tools.py, test_api.py
```

---

## API Reference

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/status` | GET | Rover telemetry (proxies bridge) |
| `/command` | POST | Send natural language command |
| `/sessions` | GET | Session history |
| `/hazards` | GET | Hazard map |
| `/storm/activate` | POST | Enable storm mode |
| `/storm/deactivate` | POST | Disable storm mode |
| `/skills` | GET | List loaded skills |
| `/ws/stream` | WebSocket | Live telemetry stream |

---

## Hackathon Context

Built for **Nous Research hackathon** to showcase Hermes Agent capabilities: tool calling, memory, skills, and multi-modal control of a Mars rover simulation.

---

## Credits

- **Nous Research** — Hermes Agent
- **Gazebo** — Simulation
- **ROS 2** — Middleware
- **Snehal (@SnehalRekt)** — Build plan

---

## License

MIT
