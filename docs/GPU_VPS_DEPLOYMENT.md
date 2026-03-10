# Hermes Rover GPU VPS Deployment

This repo already runs headless. The VPS path in this document keeps the Hermes agent headless and adds Gazebo remote visualization by combining:

- Gazebo headless rendering with `--headless-rendering`
- A Gazebo websocket visualization server on port `9002`
- Your existing bridge/API/Hermes stack

As of March 10, 2026, the safest Ubuntu stack for this repo is:

- Ubuntu `24.04` LTS on the VPS
- NVIDIA GPU driver installed on the host
- ROS 2 `Jazzy` if you want `ros_gz_bridge`
- Gazebo `Harmonic` for ROS 2 Jazzy compatibility

Official references:

- Gazebo getting started: `https://gazebosim.org/docs/all/getstarted/`
- Gazebo headless rendering: `https://gazebosim.org/api/sim/9/headless_rendering.html`
- Gazebo web visualization: `https://gazebosim.org/api/sim/10/web_visualization.html`
- Gazebo + ROS 2 install notes: `https://gazebosim.org/docs/harmonic/ros_installation/`
- SDFormat tutorials: `https://sdformat.org/tutorials/`

## 1. Provision the VPS

Pick a Linux GPU VPS with:

- Ubuntu 24.04
- 1 NVIDIA GPU
- at least 4 vCPU / 16 GB RAM
- public SSH access

## 2. Install the NVIDIA driver

On the VPS:

```bash
sudo apt update
sudo apt install -y ubuntu-drivers-common
sudo ubuntu-drivers install
sudo reboot
```

After reconnecting:

```bash
nvidia-smi
```

If `nvidia-smi` fails, stop here and fix the driver before touching Gazebo.

## 3. Install ROS 2 Jazzy and Gazebo Harmonic

Follow the current official ROS 2 Jazzy Ubuntu install guide first, then install Gazebo integration:

```bash
sudo apt update
sudo apt install -y ros-jazzy-desktop ros-jazzy-ros-gz
```

If you do not need `ros_gz_bridge`, you can run this repo with Gazebo alone, but the current `scripts/start_sim.sh` path expects ROS 2 to exist.

## 4. Clone the repo and install Python deps

```bash
git clone <your-repo-url> hermes-mars-rover
cd hermes-mars-rover
python3.11 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

The launch scripts now prefer `.venv/bin/python` automatically when the virtualenv exists.

Install the `hermes` CLI in the same environment you already use locally. If you already have a working local install process, mirror that on the VPS before starting the rover agent.

## 5. Configure environment

Create `.env` from your local working config:

```bash
cp .env.example .env
```

Fill in at least the values you already use locally, for example:

- `OPENROUTER_API_KEY`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_ALLOWED_USERS`
- `ROVER_API_KEY` if you want the API protected

## 6. Start the VPS visualization stack

For the full rover stack:

```bash
source /opt/ros/jazzy/setup.bash
./scripts/start_all_vps.sh
```

For simulation only:

```bash
source /opt/ros/jazzy/setup.bash
./scripts/start_sim_vps.sh
```

What these wrappers do:

- switch the world to [`simulation/worlds/mars_terrain_websocket.sdf`](../simulation/worlds/mars_terrain_websocket.sdf)
- run Gazebo in server-only mode
- enable `--headless-rendering`
- expose the websocket visualization server on port `9002`

## 7. View Gazebo remotely in the browser

Do not expose port `9002` publicly unless you put TLS/auth in front of it. The simpler and safer path is an SSH tunnel from your laptop:

```bash
ssh -L 9002:127.0.0.1:9002 -L 8000:127.0.0.1:8000 <user>@<vps-ip>
```

Then open:

- `https://app.gazebosim.org/visualization`

Connect the page to:

- `ws://127.0.0.1:9002`

You should now see the Mars world and rover while the Hermes agent continues driving it headlessly on the VPS.

## 8. Optional dashboard access

If you also want the existing web dashboard:

```bash
cd dashboard
npm install
npm run build
npm run start -- --hostname 0.0.0.0 --port 3000
```

Then either expose port `3000` through your firewall or add it to your SSH tunnel.

## 9. Recording video

The simplest recording path is local:

- view Gazebo through the browser visualization
- record your screen with OBS or your OS recorder

That avoids setting up a remote desktop stack just to capture video.

## 10. Troubleshooting

- Black or empty visualization:
  Make sure the VPS really has a working NVIDIA driver and that `nvidia-smi` succeeds.
- Gazebo starts but sensors do not render:
  Confirm you launched with `./scripts/start_all_vps.sh` or `./scripts/start_sim_vps.sh`, not the older headless-only scripts.
- `hermes: command not found`:
  Install the Hermes CLI into the same `.venv` or PATH used by the launcher.
- API starts without env vars:
  Use `./scripts/start_api.sh` or `./scripts/start_all.sh`; both now load `.env` before launching.


