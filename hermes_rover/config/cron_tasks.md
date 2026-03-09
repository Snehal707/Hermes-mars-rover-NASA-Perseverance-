# Hermes Cron Jobs — Rover Session Reports

Hermes Agent includes a built-in cron scheduler. Use `hermes cron` commands to run periodic session reports and deliver them via Telegram.

---

## Prerequisites

- **Telegram gateway:** Run `hermes gateway setup` and configure Telegram.
- **Custom tools:** Ensure `hermes_rover/tools` is set as `custom_tools_dir` in your Hermes config (`~/.hermes/config.yaml`) so the `generate_report` tool is available.
- **API keys:** `OPENROUTER_API_KEY` (or other LLM provider) and `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ALLOWED_USERS` in `~/.hermes/.env`.

---

## Job 1: Session Report Every 4 Hours

Generates a report of rover activity for the last 4 hours and sends it to Telegram.

```bash
hermes cron add "Session report every 4 hours" --schedule "0 */4 * * *" --deliver telegram --message "Generate a session report for the last 4 hours including distance traveled, hazards found, skills used, and terrain explored. Format as a clean summary."
```

Cron schedule: `0 */4 * * *` = every 4 hours (0:00, 4:00, 8:00, 12:00, 16:00, 20:00).

---

## Job 2: Daily Summary

Generates a daily summary of all rover sessions and sends it to Telegram.

```bash
hermes cron add "Daily summary" --schedule "0 20 * * *" --deliver telegram --message "Generate a daily summary of all rover sessions today."
```

Cron schedule: `0 20 * * *` = every day at 20:00.

---

## Managing Cron Jobs

- List jobs: `hermes cron list` (or equivalent)
- Remove a job: `hermes cron remove <job_name>` (or equivalent)

Hermes cron syntax may vary by version. If `--schedule`, `--deliver`, or `--message` differ, adjust per [Hermes docs](https://hermes-agent.nousresearch.com/docs/).
