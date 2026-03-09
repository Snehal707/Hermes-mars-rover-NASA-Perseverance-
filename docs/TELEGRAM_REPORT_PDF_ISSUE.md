# Telegram “Report in PDF” Sends Text Only — Detailed Issue

> Update (2026-03-09): Telegram runs in gateway-only mode.
> `scripts/start_telegram.sh` is deprecated and forwards to `scripts/start_gateway_pdf.sh`.
> Do not run a separate custom Telegram poller alongside gateway.


## What you see

- **User (Snehal):** “Send me the report in pdf”
- **Hermes Mars Rover:** Long text describing the report + “📎 File: /home/snehal007/hermes-mars-rover/MARS_RESEARCH_REPORT.pdf”
- **Problem:** The **actual PDF file is never sent** in Telegram; only text (and a path on the server) is sent.

---

## Why this happens: two different Telegram paths

There are **two ways** Telegram can talk to your project:

### Path 1: Custom Telegram bot (Option B) — `telegram_bot/bot.py`

- **Code:** `scripts/start_telegram.sh` → `python3 -m telegram_bot.bot`
- **Flow:** Telegram message → **this bot** → bot’s `text_handler` or `report_cmd`
- **Report/PDF behavior:**
  - **`/report`** command: Bot calls API `GET /report/pdf` and, if it gets bytes, sends the file with `reply_document(...)` ✅
  - **“Send me the report in pdf”** (plain text): We added logic so the bot should call `_api_report_pdf()` and, if the API returns PDF bytes, send them with `reply_document(...)`. If the API is unreachable or returns no PDF, the bot falls back to `_api_command(...)`.

So for **Path 1**, the bot **can** send the real PDF only if:
1. The **API is running** (e.g. `uvicorn api.main:app --port 8000`) and reachable at `API_URL` (default `http://localhost:8000`).
2. The **bot process** you’re running is the **updated** `telegram_bot.bot` (restarted after the code change).
3. `GET /report/pdf` returns **200** with PDF bytes (fpdf2 installed, report content built successfully).

If any of these fail, `_api_report_pdf()` returns `None` and the bot falls back to the next step (text report or agent).

### Path 2: Hermes Gateway (Telegram ↔ Hermes agent)

- **Setup:** `hermes gateway setup` and Telegram configured there (see e.g. `hermes_rover/config/cron_tasks.md`).
- **Flow:** Telegram message → **Hermes Gateway** → **Hermes agent** (`hermes chat` / rover agent) → agent uses tools (terminal, write_file, etc.) → agent’s **text** reply → Gateway → Telegram.
- **What the agent can do:** Run commands, create files (e.g. PDF in `~/hermes-mars-rover/`), and **only send text** back. The Gateway sends the agent’s **message** to the user, not arbitrary files from disk. So the user gets “Here’s your report…” and “File: …/MARS_RESEARCH_REPORT.pdf” as **text**, and no PDF attachment.

The reply you quoted (“Here’s your Mars Rover Research Report in PDF format… 📎 File: /home/snehal007/hermes-mars-rover/MARS_RESEARCH_REPORT.pdf”) is exactly the **agent** answering: it created a PDF on the server and described it. So that reply is coming from **Path 2** (Hermes Gateway → agent), not from the Option B bot.

---

## Conclusion: which path is handling the message?

- If the reply is the **long agent-style message** (with file path, mission summary, etc.), that message is coming from the **Hermes Gateway + agent** (Path 2).
- The change we made only affects **Path 1** (Option B bot in `telegram_bot/bot.py`). So if Snehal’s message is handled by the **Gateway**, our bot code **never runs** for that chat, and the PDF will never be sent by the current fix.

---

## What to do (for you or Codex)

### 1. Confirm which Telegram connection is used

- If you use **only** the custom bot: start it with `bash scripts/start_telegram.sh` (or via `scripts/start_all.sh`). Then the same bot must be the one receiving “Send me the report in pdf.” Ensure **API is running** and **bot was restarted** after the PDF fix.
- If you use **Hermes Gateway** for chat: then “Send me the report in pdf” is handled by the **Gateway → agent**. The fix must be there (see below), not only in Option B.

### 2. If you use the **Option B bot** (Path 1)

- Ensure the **API** is up: `GET http://localhost:8000/report/pdf` should return a PDF (e.g. in browser or `curl`).
- Set `API_URL` for the bot if needed (e.g. if the bot runs on another host: `API_URL=http://<api-host>:8000`).
- **Restart** the Telegram bot after any code change so the “report in pdf” detection and `_api_report_pdf()` + `reply_document` logic are used.
- In the bot, when the user clearly asks for “report in pdf”, the code should **not** call the agent; it should only try API PDF (and optionally text report fallback). The relevant code is in `telegram_bot/bot.py`: `_wants_report_pdf()`, and in `text_handler` the block that calls `_api_report_pdf()` and `reply_document`.

### 3. If you use **Hermes Gateway** (Path 2)

- The agent **cannot** send a file to Telegram by itself; it can only return text (and the Gateway sends that text).
- To send the **real** PDF:
  - **Option A:** In the Gateway (or whatever layer sits between Telegram and the agent), add a **pre-check**: if the user message is “report in pdf” (or similar), **don’t** forward to the agent; instead call your backend `GET /report/pdf`, then use the Telegram API to **send the PDF as a document** (e.g. `sendDocument`), then optionally send a short text. That requires access to the Gateway code or a small “adapter” that handles this before invoking the agent.
  - **Option B:** Keep using the **Option B bot** for report requests: e.g. tell users to use the **`/report`** command for PDF (the bot sends the file from the API), or ensure that when they write “report in pdf” they are talking to the **Option B bot** (different bot token or same token but only one integration active).

### 4. Quick user workaround

- Use the **`/report`** command in Telegram. That path is wired to send the PDF file from the API when the API is up and the bot is Option B.

---

## Code references (Option B bot)

- **PDF detection (plain text):** `telegram_bot/bot.py` — `_wants_report_pdf(text)` and the block in `text_handler` that calls `_api_report_pdf()` and `reply_document`.
- **PDF from API:** `telegram_bot/bot.py` — `_api_report_pdf()` (GET `API_URL/report/pdf`).
- **API PDF endpoint:** `api/main.py` — `GET /report/pdf`, implemented with fpdf2.

---

## Summary

- **Symptom:** User asks for “report in pdf” in Telegram and gets only text (and a server file path), no PDF file.
- **Cause:** Either (1) the message is handled by **Hermes Gateway → agent** (Path 2), which can only send text, or (2) the message is handled by the **Option B bot** (Path 1) but the API PDF call fails (API down, wrong URL, or bot not restarted), so the bot falls back to agent/text.
- **Fix:** Use **`/report`** for PDF when using Option B; or implement “report in pdf” handling in the **Gateway** (call API, send PDF with Telegram `sendDocument`); or ensure only Option B handles that phrase and that API + bot are running and up to date.
