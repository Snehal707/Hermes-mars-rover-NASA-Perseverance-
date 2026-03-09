# Apple Watch / Siri Integration

Control the HERMES Mars Rover from Apple Watch using Siri voice commands via iOS Shortcuts. No code required — only configuration.

---

## Section A — Expose API

Your FastAPI server runs on `localhost:8000`. To reach it from iPhone and Apple Watch, expose it with a public URL.

### Option A: Cloudflare Tunnel (Recommended, Free)

On your Linux server (or WSL):

```bash
# Install cloudflared
curl -L --output cloudflared.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb && dpkg -i cloudflared.deb

# Login (opens browser)
cloudflared tunnel login

# Create tunnel
cloudflared tunnel create mars-rover

# Route DNS (replace rover.yourdomain.com with your domain)
cloudflared tunnel route dns mars-rover rover.yourdomain.com

# Run tunnel (forward to local API)
cloudflared tunnel run --url http://localhost:8000 mars-rover
```

Replace `rover.yourdomain.com` with your actual domain. Ensure the API is running on port 8000 before starting the tunnel.

### Option B: ngrok (Quick Testing)

```bash
ngrok http 8000
```

Copy the HTTPS URL (e.g. `https://abc123.ngrok.io`) and use it as `YOUR_DOMAIN` in the Shortcuts.

---

## Section B — iOS Shortcuts (NO CODE)

Create these Shortcuts in the **Shortcuts** app. Each works on Apple Watch automatically.

### Shortcut 1: "Move Rover"

1. Open Shortcuts app → **New Shortcut**
2. Add action: **Ask for Input** → Type: Text → Prompt: `Command?`
3. Add action: **Get Contents of URL**
   - URL: `https://YOUR_DOMAIN/command`
   - Method: POST
   - Request Body: JSON → `{"text": "[Provided Input]"}`
4. Add action: **Get Dictionary Value** → key: `response`
5. Add action: **Show Result**
6. Rename shortcut: **Move Rover**
7. Settings → enable **Show on Apple Watch**

### Shortcut 2: "Rover Photo"

1. New Shortcut
2. Add action: **Get Contents of URL**
   - URL: `https://YOUR_DOMAIN/command`
   - Method: POST
   - Request Body: JSON → `{"text": "take a photo with navcam"}`
3. Add action: **Show Result**
4. Rename: **Rover Photo**
5. Enable **Show on Apple Watch**

### Shortcut 3: "Rover Status"

1. New Shortcut
2. Add action: **Get Contents of URL**
   - URL: `https://YOUR_DOMAIN/status`
   - Method: GET
3. Add action: **Get Dictionary Value** → key: `position`
4. Add action: **Show Result**
5. Rename: **Rover Status**
6. Enable **Show on Apple Watch**

### Shortcut 4: "Stop Rover"

1. New Shortcut
2. Add action: **Get Contents of URL**
   - URL: `https://YOUR_DOMAIN/command`
   - Method: POST
   - Request Body: JSON → `{"text": "emergency stop"}`
3. Add action: **Show Result**
4. Rename: **Stop Rover**
5. Enable **Show on Apple Watch**

Replace `YOUR_DOMAIN` with your cloudflared or ngrok URL (e.g. `rover.yourdomain.com`).

---

## Section C — Siri Usage

Once Shortcuts are created and enabled for Apple Watch:

- **"Hey Siri, Move Rover"** — then say your command (e.g. "forward 5 meters")
- **"Hey Siri, Rover Status"** — shows position and telemetry
- **"Hey Siri, Rover Photo"** — triggers NavCam photo capture
- **"Hey Siri, Stop Rover"** — emergency stop

Works from Apple Watch, iPhone, iPad, and Mac.
