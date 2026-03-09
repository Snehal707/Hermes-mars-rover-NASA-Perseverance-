# HERMES Mars Rover

AI-powered Mars rover simulation with Hermes Agent, Gazebo, FastAPI, Telegram, and a Next.js dashboard.

## Highlights

- Natural language rover control through Hermes CLI and Telegram
- Live telemetry via API and WebSocket stream
- Mars simulation in Gazebo with rover sensors
- Session reports, including PDF export endpoint
- Web dashboard for mission control

## Architecture

- `simulation/`: Gazebo worlds and rover models
- `bridge/`: sensor bridge service (default `:8765`)
- `api/`: command + telemetry API (default `:8000`)
- `dashboard/`: Next.js mission dashboard (default `:3000`)
- `hermes_rover/`: rover integration, memory, gateway helpers
- `scripts/`: startup and orchestration scripts

## Prerequisites

- Ubuntu/WSL with:
  - Python 3.10+ (3.11 recommended)
  - Node.js 18+
  - Gazebo Harmonic/Jetty
  - ROS 2 Humble/Jazzy (for your local sim setup)

## Quick Start

1. Clone and enter repo:
   ```bash
   git clone <your-repo-url>
   cd HERMES-MARS-ROVER
   ```
2. Install Python dependencies:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
3. Install dashboard dependencies:
   ```bash
   cd dashboard
   npm install
   cd ..
   ```
4. Configure environment:
   ```bash
   cp .env.example .env
   ```
   Fill `.env` with your keys (`OPENROUTER_API_KEY`, `TELEGRAM_BOT_TOKEN`, etc.).
5. Start services:
   ```bash
   bash scripts/start_all.sh
   ```

## Common Service Commands

- Start simulation only: `bash scripts/start_sim.sh`
- Start bridge only: `bash scripts/start_bridge.sh`
- Start API only: `bash scripts/start_api.sh`
- Start gateway only: `bash scripts/start_gateway_pdf.sh`
- Start Hermes CLI: `bash scripts/start_hermes.sh`
- Start dashboard: `cd dashboard && npm run dev`

## API Endpoints (Core)

- `GET /status`
- `GET /telemetry`
- `POST /command`
- `POST /drive`
- `GET /sessions`
- `GET /report`
- `GET /report/pdf`
- `GET /report/pdf/save`
- `WS /ws/stream`

Open docs at: `http://localhost:8000/docs`

## Testing

```bash
python3 -m pytest tests/ -q
```

## Security Notes

- Never commit real tokens or `.env` files.
- Use `ROVER_API_KEY` in production-like deployments.
- Restrict Telegram bot access with `TELEGRAM_ALLOWED_USERS`.

## License

MIT - see [LICENSE](LICENSE)

