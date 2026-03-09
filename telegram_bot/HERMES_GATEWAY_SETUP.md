# Hermes Gateway — Telegram Setup (Option A)

Use Hermes' built-in Telegram integration so you can control the rover and talk to the AI from Telegram. Voice messages are auto-transcribed and processed as commands.

---

## Step 1: Add environment variables to Hermes config

Create or edit the Hermes config directory and env file:

- **Linux/macOS:** `~/.hermes/.env`
- Or use your project `.env` in the repo root if Hermes is configured to load it.

Add these variables:

```bash
TELEGRAM_BOT_TOKEN=your_bot_token_from_botfather
TELEGRAM_ALLOWED_USERS=123456789,987654321
```

- **TELEGRAM_BOT_TOKEN:** Create a bot via [@BotFather](https://t.me/BotFather) on Telegram (`/newbot`), then paste the token here.
- **TELEGRAM_ALLOWED_USERS:** Comma-separated list of Telegram user IDs. Get your ID by messaging [@userinfobot](https://t.me/userinfobot). Only these users can talk to the rover via this bot.

---

## Step 2: Run Hermes gateway setup

From your project root (or wherever you run Hermes):

```bash
hermes gateway setup
```

When prompted:

1. Select **Telegram** as the gateway type.
2. Paste your **TELEGRAM_BOT_TOKEN** when asked.
3. Paste your **TELEGRAM_ALLOWED_USERS** (e.g. your numeric user ID) when asked.

This saves the configuration for the next step.

---

## Step 3: Run the gateway

Start the Telegram gateway:

```bash
hermes gateway
```

The bot will start polling. You can now open Telegram, find your bot, and send messages.

**Optional (Linux):** Install as a systemd service so it runs in the background:

```bash
hermes gateway install
```

---

## Step 4: How voice messages work

- When you send a **voice message** in Telegram, Hermes gateway **automatically transcribes** it and processes the result as a text command.
- No extra bot code or API is required for voice when using the Hermes gateway.
- You can say things like "move forward 5 meters" or "what's the rover status?" and the AI will use the rover tools to respond.

---

## Step 5: Custom rover tools with the gateway

When `hermes gateway` runs, it uses the same Hermes config as `hermes chat`. So:

- Ensure your Hermes config (e.g. `hermes_rover/config/hermes_config.yaml`) has **custom_tools_dir** pointing to `hermes_rover/tools`.
- Then the gateway has access to **drive_rover**, **read_sensors**, and **navigate_to** (and any other tools in that directory).
- Start the gateway from the project root with `PYTHONPATH` including the project root so Hermes can load `hermes_rover.tools`.

Example: from repo root,

```bash
export PYTHONPATH="$PWD"
hermes gateway
```

If your config file is not the default, pass it explicitly if Hermes supports it (e.g. `--config hermes_rover/config/hermes_config.yaml`).

---

## Summary

| Step | Action |
|------|--------|
| 1 | Add `TELEGRAM_BOT_TOKEN` and `TELEGRAM_ALLOWED_USERS` to `~/.hermes/.env` (or project `.env`) |
| 2 | Run `hermes gateway setup` and select Telegram, paste token and user IDs |
| 3 | Run `hermes gateway` (or `hermes gateway install` on Linux for systemd) |
| 4 | Voice messages are auto-transcribed and handled like text |
| 5 | Rover tools are available because the gateway uses the same config as `hermes chat` |

After this, you can control the Mars rover and chat with the AI from Telegram using text and voice.
