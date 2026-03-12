# 🚀 HERMES — AI-Powered Mars Rover (NASA Perseverance Simulation)

> Built on top of [NousResearch's open-source Hermes Agent framework](https://github.com/NousResearch/hermes-agent), this project is an autonomous, AI-native Mars rover agent using the **real NASA Perseverance model**. It runs physics-accurate Martian simulation via **Gazebo**, is controlled through natural language, voice, and Telegram, and features full memory, self-improvement, and PDF reporting.

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Gazebo](https://img.shields.io/badge/Simulation-Gazebo%20Harmonic-orange)](https://gazebosim.org)
[![FastAPI](https://img.shields.io/badge/API-FastAPI-green)](https://fastapi.tiangolo.com)

---

## 🔭 What is Hermes?

**Hermes** is a fully autonomous, AI-driven Mars rover agent that:

- Simulates the **real NASA Perseverance rover** (DAE mesh model) in a physics-accurate Martian environment
- Runs **autonomous missions** driven by natural language via CLI, Telegram, or voice
- Makes **real-time decisions** using tools, skills, and structured memory
- **Learns from past missions** — avoids previously discovered hazards, improves behavior over time
- Delivers **PDF mission reports and camera images** as real Telegram attachments
- Can be fully controlled by **voice commands** through Telegram

---

## 🛸 Rover Model — NASA Perseverance

Hermes uses the **real NASA Perseverance rover model**, not primitive shapes or placeholders.

| Property | Detail |
|----------|--------|
| **Model** | NASA Perseverance Mars Rover |
| **Source** | `simulation/models/perseverance/` — DAE mesh + SDF |
| **Simulation Engine** | Gazebo Harmonic / Fortress |
| **Sensor Suite** | IMU, Odometry, NavCam, MastCam, HazCam (front/rear), SuperCam LIDAR, Contact sensor |
| **Drive System** | 6-wheel rocker-bogie diff-drive (via Gazebo diff-drive plugin) |

The Perseverance model’s `model.sdf` defines:

- A realistic mass/inertia for the chassis (~1025 kg).
- Six wheels with correct radii, friction, and contact surfaces.
- A diff-drive plugin that converts `/rover/cmd_vel` into wheel motions and publishes odometry on `/rover/odometry`.
- Sensors publishing to:
  - `/rover/imu`
  - `/rover/navcam_left`
  - `/rover/mastcam`
  - `/rover/hazcam_front`
  - `/rover/hazcam_rear`
  - `/rover/lidar`
  - `/rover/contact`

### 🪐 Mars Physics Simulation

The simulation enforces accurate Martian physical constants:

| Physics Parameter | Mars Value | Effect in Simulation |
|-------------------|------------|----------------------|
| **Gravity** | −3.72 m/s² (38% of Earth) | Rover dynamics, jump/fall behavior |
| **Terrain friction** | Low (loose regolith-like) | Wheel slip, traction limits |
| **Slope response** | Rocker-bogie geometry | Passive suspension over rocks |
| **Atmosphere** | Thin CO₂ atmosphere model | No significant aerodynamic drag; storms modeled logically via skills |
| **Inertia** | True Perseverance mass/geometry | Authentic momentum, tipping behavior |
| **LIDAR range** | Calibrated for Martian distances | Hazard detection at correct scales |
| **IMU tilt thresholds** | Safety-tuned for Mars gravity | Auto-stop on dangerous inclines |

World files like `simulation/worlds/mars_terrain_websocket.sdf` define:

- Mars gravity (`<gravity>0 0 -3.721</gravity>`).
- Thin atmosphere.
- A large Mars terrain plane with rocks and a modeled cliff/drop-off region.
- Websocket visualization plugin (port `9002`) for headless remote viewing.

Every physics tick runs under Martian gravity, so the rover’s motion, suspension behavior, and hazard responses are physically consistent with Mars.

---

## 🧠 Autonomous Missions & Decision-Making

Hermes is not a remote-controlled robot — it is an **AI agent that thinks, plans, and acts on its own**.

### How Autonomous Missions Work

```
User (natural language) ──▶ Hermes Mission Agent (mission_agent.py)
                                    │
                          ┌─────────▼──────────┐
                          │  Mission Planning   │
                          │  (breaks into steps)│
                          └─────────┬──────────┘
                                    │
             ┌──────────────────────┼───────────────────────┐
             ▼                      ▼                       ▼
      navigate_to()          read_sensors()        check_hazards()
      drive_rover()          capture_camera()      rover_memory()
      generate_report()      send_message()        [+ more tools]
```

You send Hermes a high-level command like:

> *"Explore the nearby crater, avoid all hazards, take photos, and send me a PDF report on Telegram."*

Hermes **autonomously**:
1. Plans the mission into steps.
2. Calls navigation tools to drive the rover.
3. Continuously reads IMU/LIDAR/Odometry sensors.
4. Queries memory for known hazard zones.
5. Applies skills for terrain, obstacles, storms, cliffs.
6. Captures and delivers images to Telegram.
7. Generates and sends a PDF mission report.

### Tools Available to Hermes

| Tool | Purpose |
|------|---------|
| `navigate_to` | Drive to target coordinate using odometry + hazard checks |
| `drive_rover` | Low-level velocity/heading commands (cmd_vel) |
| `read_sensors` | IMU, odometry, LIDAR readings |
| `check_hazards` | Real-time obstacle/cliff detection |
| `capture_camera_image` | Take photo, save to disk, return absolute file path + MEDIA tag |
| `generate_report` | Create structured mission report |
| `rover_memory` | Query/save hazards, terrain, sessions, behaviors |
| `send_message` | Deliver text/media (PDFs/images) to Telegram |

---

## 🎯 Skills — Structured Decision Playbooks

Skills in `hermes_rover/skills/` are **pre-built decision strategies** Hermes applies when facing specific situations:

### `terrain_assessment`
Adjusts rover speed based on IMU tilt readings:
- **Flat** (< ~0.2 rad / 11°) → normal speed.
- **Mild slope** (~0.2–0.35 rad) → reduced speed.
- **Steep** (~0.35–0.52 rad) → crawl speed + heightened alert.
- **Dangerous** (> ~0.52 rad) → emergency stop, consider reversing.

### `obstacle_avoidance`
Reacts to LIDAR proximity data:
- Near obstacle detected → slow, assess, reroute.
- Blocked path → attempt alternate heading / waypoints.
- Repeated blockage → log hazard, request new mission plan.

### `storm_protocol`
Dust-storm emergency sequence:
1. Immediately halt all motion.
2. Log storm event with coordinates and timestamp.
3. Alert user via Telegram.
4. Monitor storm-related signals periodically.
5. Resume mission once conditions are safe.

### `cliff_protocol`
Cliff/drop-off detection response:
1. Emergency stop before edge.
2. Reverse to safe distance.
3. Mark location as cliff hazard in memory.
4. Replan route around the hazard.

### `camera_telegram_delivery`
Automated image delivery:
1. Capture image with `capture_camera_image` → save to media cache.
2. Extract absolute file path and `MEDIA:/absolute/path/image.jpg` tag.
3. Use `send_message` with that tag and a caption.
4. Hermes gateway sends file as a real Telegram photo attachment.

---

## 🧩 Memory System — Learning from Past Missions

Hermes has **persistent structured memory** in `hermes_rover/memory/rover_memory.db` (SQLite).

### What Gets Remembered

| Memory Type | Stored Data |
|-------------|-------------|
| **Hazard Map** | Coordinates, hazard type, severity, description, session ID |
| **Terrain Logs** | Position, terrain type, traversability score, notes |
| **Session Logs** | Distance covered, photos taken, hazards found, skills used, summary |
| **Learned Behaviors** | Trigger → action pairs with success/failure counters |

### How Hermes Uses Memory

Before entering a zone:

```python
rover_memory.check_area(x, y, radius=5.0)
```

After finding something new:

```python
rover_memory.save_discovery(x, y, hazard_type="cliff", severity="high")
```

After a successful strategy:

```python
rover_memory.save_behavior(trigger="steep_slope", behavior_action="reduce_speed_50pct")
```

On later missions, Hermes can call:

```python
rover_memory.get_behaviors()
```

to recall learned behaviors and apply them again.

### Avoiding Dangerous Zones from Past Missions

When planning routes, Hermes can:
1. Query the hazard map near the planned path (`check_area`).
2. Treat any known hazards as exclusion zones.
3. Replan navigation to route around them.

This means **every mission can make future missions safer** — the rover accumulates a growing map of danger zones it can avoid.

---

## 🔄 Self-Improvement Loop

```
Mission Execution
      │
      ▼
Encounter Problem
      │
      ▼
Solve It + Log What Worked  ──▶  save_behavior(trigger, action)
      │
      ▼
Next Time Similar Situation ──▶  get_behaviors() → apply best known action
```

The system prompt and context instruct Hermes to:

- Log what went wrong during missions.
- Create or update SKILL.md files when it solves a new class of problem.
- Track which behaviors worked and reuse them in future missions.

---

## 📄 PDF Reports via Telegram

### Generating a PDF

Hermes calls the FastAPI endpoint:

```http
GET /report/pdf/save
```

This uses `fpdf2` to render a formatted PDF containing:

- Mission summary (date, duration, distance).
- Hazards encountered (with coordinates and severity).
- Skills applied.
- Terrain traversability notes.
- Session statistics and conclusions.

The PDF is saved to `~/.hermes/document_cache/` or `reports/`, and the **absolute path is returned**.

### Sending to Telegram

Hermes includes the path in its reply as:

```text
MEDIA:/home/user/.hermes/document_cache/mission_report_2026.pdf
```

The Hermes gateway/Telegram adapter reads the `MEDIA:` tag and sends the actual **PDF file as a Telegram attachment** — not just text.

**Example command:**

> *"Run a full mission and send me the detailed research report as a PDF on Telegram."*

---

## 🎙️ Voice Command Control via Telegram

You can control Hermes entirely with your voice through Telegram.

### Voice Command Flow

```
Your Voice
    │
    ▼
Voice Client (mic listener)
    │   OpenAI-compatible STT API
    ▼
Transcribed Text
    │
    ▼
Hermes Gateway (Telegram)
    │
    ▼
Hermes Mission Agent
    │
    ▼
Tools / Skills / Rover Actions
```

### Setup

Configure in `.env`:

```env
VOICE_TOOLS_OPENAI_KEY=your_key_here
# or reuse:
OPENAI_API_KEY=your_key_here
OPENAI_BASE_URL=https://api.openai.com/v1
```

### Example Voice Commands

| You Say | Hermes Does |
|---------|-------------|
| *"Hermes, explore the nearby crater and avoid cliffs."* | Plans + executes full exploration mission. |
| *"Hermes, send me a photo of the terrain ahead."* | Captures camera image, sends to Telegram. |
| *"Hermes, run a full mission and send me the PDF report."* | Completes mission + delivers PDF attachment. |
| *"Hermes, return to the lander avoiding all known danger zones."* | Plans safe return path using hazard memory. |

Because Hermes processes **text** (whether typed or from voice-to-text), voice and text commands are **equally powerful**.

---

## 🏗️ High-Level Architecture

```text
┌─────────────────────────────────────────────────────────┐
│                     USER INTERFACES                    │
│  Voice Client  │  Telegram Bot  │  CLI  │  Apple Watch │
└────────┬───────┴───────┬────────┴───┬───┴──────────────┘
         │               │            │
         └───────────────▼────────────┘
                  Hermes Gateway
                         │
              ┌──────────▼──────────┐
              │   Hermes Mission     │
              │   Agent (AI Core)    │
              │  mission_agent.py    │
              └──────────┬──────────┘
                         │  Tools + Skills + Memory
              ┌──────────▼──────────┐
              │   FastAPI Rover API  │
              │     api/main.py      │
              │       :8000          │
              └──────────┬──────────┘
                         │
              ┌──────────▼──────────┐
              │  WebSocket Bridge   │
              │       bridge/       │
              │       :8765         │
              └──────────┬──────────┘
                         │
         ┌───────────────▼───────────────┐
         │    Gazebo Simulation           │
         │  NASA Perseverance Model       │
         │  Mars Physics (−3.72 m/s²)    │
         │  IMU · LIDAR · Cameras · Odom │
         └───────────────────────────────┘
```

---

## 📁 Project Structure

```text
Hermes-mars-rover-NASA-Perseverance-/
├── simulation/                  # Gazebo worlds + Perseverance model (SDF + DAE mesh)
├── bridge/                      # WebSocket bridge: Gazebo ↔ HTTP API (:8765)
├── api/                         # FastAPI rover API (:8000) — commands, telemetry, PDF
├── hermes_rover/
│   ├── tools/                   # navigate_to, drive_rover, sensors, camera, memory, reports
│   ├── skills/                  # terrain_assessment, obstacle_avoidance, storm/cliff/camera protocols
│   ├── memory/
│   │   ├── memory_manager.py    # Hazard map, terrain logs, session logs, behaviors
│   │   └── rover_memory.db      # Persistent SQLite database
│   ├── mission_agent.py         # Autonomous mission planner + executor
│   └── config/
│       ├── system_prompt.md     # Hermes AI persona + instructions
│       └── context.md           # Tools/skills context injection
├── hermes-agent/                # Upstream Hermes Agent framework + gateway
├── telegram_bot/                # Telegram bot entrypoint
├── dashboard/                   # Next.js mission dashboard (:3000)
├── apple_watch/                 # Apple Watch control interface
├── reports/                     # Generated PDF mission reports
├── docs/                        # Deployment guides (local + GPU VPS)
├── scripts/                     # Startup scripts (start_all.sh, start_sim.sh, etc.)
├── tests/                       # Pytest test suite
├── .env.example                 # Environment variable template
├── requirements.txt             # Python dependencies
└── README.md
```

---

## ⚡ Quick Start

### 1. Clone & Install

```bash
git clone https://github.com/Snehal707/Hermes-mars-rover-NASA-Perseverance-.git
cd Hermes-mars-rover-NASA-Perseverance-

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cd dashboard && npm install && cd ..
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env — fill in LLM keys, Telegram token, API URLs, etc.
```

### 3. Start Everything

```bash
bash scripts/start_all.sh
```

Or step by step:

```bash
bash scripts/start_sim.sh          # Gazebo simulation
bash scripts/start_bridge.sh       # WebSocket bridge
bash scripts/start_api.sh          # FastAPI rover API
bash scripts/start_gateway_pdf.sh  # Hermes Gateway (Telegram)
bash scripts/start_hermes.sh       # Hermes CLI / mission agent
cd dashboard && npm run dev        # Next.js dashboard
```

---

## 🔑 Environment Variables

Key variables in `.env.example`:

| Variable | Purpose |
|----------|---------|
| `OPENROUTER_API_KEY` | Primary LLM reasoning via OpenRouter |
| `OPENAI_API_KEY` | OpenAI / OpenAI-compatible API key (LLM/voice) |
| `OPENAI_BASE_URL` | Base URL for OpenAI-compatible APIs |
| `VOICE_TOOLS_OPENAI_KEY` | Dedicated key for voice commands (optional) |
| `TELEGRAM_BOT_TOKEN` | BotFather token |
| `TELEGRAM_ALLOWED_USERS` | Comma-separated Telegram user IDs |
| `TELEGRAM_HOME_CHANNEL` | Home channel/chat for broadcasts |
| `API_URL` | FastAPI URL (default: `http://localhost:8000`) |
| `BRIDGE_URL` | Bridge URL (default: `http://localhost:8765`) |
| `ROVER_API_KEY` | API authentication key |
| `FIRECRAWL_API_KEY` | Firecrawl research helper (optional) |
| `FAL_KEY` | Fal.ai media generation (optional) |
| `ELEVENLABS_API_KEY` | TTS voice output (optional) |
| `SUPABASE_URL` / `SUPABASE_KEY` | Dashboard persistence (optional) |
| `GZ_SIM_RESOURCE_PATH` | Path to Gazebo simulation resources (`./simulation/models`) |
| `ROS_DOMAIN_ID` | ROS 2 domain separation |
| `HERMES_SIM_WORLD` | World file (e.g. `mars_terrain_websocket.sdf`) |
| `HERMES_SIM_SERVER_ONLY` | `true` for server-only / headless |
| `HERMES_SIM_HEADLESS_RENDERING` | `true` to enable headless camera rendering |
| `HERMES_SIM_REALTIME` | Real-time factor toggle |
| `HERMES_SIM_VERBOSITY` | Logging verbosity (0–4) |
| `HERMES_REASONING_EFFORT` | LLM reasoning depth (`low`, `medium`, `high`) |

Never commit your `.env` file or real secrets.

---

## 🌐 Core API Reference

Some key FastAPI endpoints (see `api/main.py` for full list):

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/status` | GET | Health check + rover status |
| `/telemetry` | GET | Live sensor telemetry |
| `/command` | POST | High-level natural language command (if wired) |
| `/drive` | POST | Low-level drive command |
| `/sessions` | GET | All mission sessions |
| `/report` | GET | Text mission report |
| `/report/pdf` | GET | On-demand PDF (stream) |
| `/report/pdf/save` | GET | Generate + persist PDF, return path |
| `/ws/stream` | WS | Live telemetry WebSocket stream |

Interactive docs: `http://localhost:8000/docs`

---

## 🔒 Security

- **Never** commit `.env` or real API keys/tokens.
- Use `ROVER_API_KEY` to gate write operations in production-like deployments.
- Restrict Telegram access with `TELEGRAM_ALLOWED_USERS`.
- See `SECURITY.md` for full security guidelines.

---

## 🧪 Testing

```bash
python3 -m pytest tests/ -q
```

Covers: navigation tools, sensors, memory, and schema tests for tools like `capture_camera_image`; extend as needed for new behaviors.

---

## 📜 License

MIT — see [LICENSE](LICENSE)

---

## 🤝 Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for contribution guidelines.

---

*Built with ❤️ by [@Snehal707](https://github.com/Snehal707) — Hermes: because even on Mars, the messenger always gets through.* 