"""
Custom Telegram bot (Option B): bridge commands, status, explore, report, text and voice.
Uses python-telegram-bot v20+ (async). Access control via TELEGRAM_ALLOWED_USERS.
"""
import asyncio
import io
import os
import re
import subprocess
import tempfile
from pathlib import Path

import aiohttp
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from telegram_bot.config import (
    ALLOWED_USER_IDS,
    API_URL,
    BRIDGE_URL,
    TELEGRAM_BOT_TOKEN,
)


def _allowed(user_id: int) -> bool:
    if not ALLOWED_USER_IDS:
        return True
    return user_id in ALLOWED_USER_IDS


async def _bridge_drive(linear: float, angular: float, duration: float) -> dict | None:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{BRIDGE_URL}/drive",
                json={"linear": linear, "angular": angular, "duration": duration},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
                return None
    except Exception:
        return None


async def _bridge_status() -> dict | None:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{BRIDGE_URL}/",
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
                return None
    except Exception:
        return None


async def _api_report() -> str | None:
    """GET or POST API_URL/report; return response text or None."""
    for method in ("GET", "POST"):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.request(
                    method,
                    f"{API_URL}/report",
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    if resp.status == 200:
                        body = await resp.text()
                        return body
                    if resp.status == 404:
                        continue
                    return None
        except Exception:
            continue
    return None


async def _api_command(text: str, user_id: int) -> tuple[str | None, str | None, str | None]:
    """POST to API /command. Returns (response_text, photo_path, photo_caption) or (None, None, None)."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{API_URL}/command",
                json={"text": text, "user_id": str(user_id)},
                timeout=aiohttp.ClientTimeout(total=60),
            ) as resp:
                if resp.status != 200:
                    return None, None, None
                data = await resp.json()
                response = data.get("response") or data.get("text") or str(data)
                photo_path = data.get("photo_path")
                photo_caption = data.get("photo_caption", "Mars surface")
                return response, photo_path, photo_caption
    except Exception:
        return None, None, None


def _extract_media_tags(content: str) -> tuple[list[str], str]:
    """
    Extract MEDIA:<path> tags from text and return (paths, cleaned_text).
    Supports:
      MEDIA:/tmp/file.pdf
      MEDIA:"/path/with spaces/file.pdf"
    """
    if not content:
        return [], ""
    media_paths: list[str] = []
    pattern = r'MEDIA:(?:"([^"]+)"|([^\n\r]+))'
    for m in re.finditer(pattern, content):
        path = (m.group(1) or m.group(2) or "").strip()
        if path:
            media_paths.append(path)
    cleaned = re.sub(pattern, "", content).strip()
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return media_paths, cleaned


async def _send_media_paths(update: Update, media_paths: list[str]) -> None:
    """
    Send local media files to Telegram as native attachments.
    If a PDF path is missing, try API /report/pdf as fallback.
    """
    if not media_paths:
        return

    image_exts = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
    audio_exts = {".ogg", ".opus", ".mp3", ".wav", ".m4a"}
    video_exts = {".mp4", ".mov", ".avi", ".mkv", ".3gp"}

    for media_path in media_paths:
        p = Path(media_path)
        ext = p.suffix.lower()
        try:
            if p.is_file():
                if ext in image_exts:
                    with open(p, "rb") as f:
                        await update.message.reply_photo(photo=f)
                elif ext in audio_exts:
                    with open(p, "rb") as f:
                        if ext in {".ogg", ".opus"}:
                            await update.message.reply_voice(voice=f)
                        else:
                            await update.message.reply_audio(audio=f)
                elif ext in video_exts:
                    with open(p, "rb") as f:
                        await update.message.reply_video(video=f)
                else:
                    with open(p, "rb") as f:
                        await update.message.reply_document(document=f, filename=p.name)
                continue

            # Fallback for missing PDF path: fetch fresh report PDF from API.
            if ext == ".pdf":
                pdf_bytes = await _api_report_pdf()
                if pdf_bytes:
                    await update.message.reply_document(
                        document=io.BytesIO(pdf_bytes),
                        filename=p.name or "mars_rover_report.pdf",
                    )
                    continue

            await update.message.reply_text(f"Attachment path not found: {media_path}")
        except Exception:
            await update.message.reply_text(f"Failed to send attachment: {media_path}")


async def _send_api_response(
    update: Update,
    response: str | None,
    photo_path: str | None = None,
    photo_caption: str | None = None,
) -> None:
    """
    Send API response text and any MEDIA-tag attachments.
    """
    if not response:
        return
    media_paths, cleaned = _extract_media_tags(response)
    if cleaned:
        await update.message.reply_text(cleaned[:4000])
    await _send_media_paths(update, media_paths)
    if photo_path and os.path.isfile(photo_path):
        with open(photo_path, "rb") as f:
            await update.message.reply_photo(photo=f, caption=photo_caption or "Mars surface")


async def _transcribe_via_api(voice_path: str) -> str | None:
    """POST audio to API /transcribe. Returns transcribed text or None if unavailable."""
    try:
        with open(voice_path, "rb") as f:
            data = aiohttp.FormData()
            data.add_field("audio", f, filename=os.path.basename(voice_path))
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{API_URL}/transcribe",
                    data=data,
                    timeout=aiohttp.ClientTimeout(total=120),
                ) as resp:
                    if resp.status != 200:
                        return None
                    result = await resp.json()
                    t = result.get("text", "").strip()
                    return t if t else None
    except Exception:
        return None


def _transcribe_voice_sync(path: str) -> str:
    """Transcribe audio file via whisper CLI (subprocess). Returns transcribed text or empty string."""
    try:
        result = subprocess.run(
            ["whisper", path, "--output_format", "txt", "--output_dir", os.path.dirname(path)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return ""
        txt_path = path.rsplit(".", 1)[0] + ".txt"
        if os.path.isfile(txt_path):
            with open(txt_path, "r", encoding="utf-8") as f:
                return f.read().strip()
        return (result.stdout or "").strip()
    except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
        return ""


async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _allowed(update.effective_user.id):
        await update.message.reply_text("Not authorized.")
        return
    await update.message.reply_text(
        "HERMES Mars Rover Control\n\n"
        "Commands:\n"
        "/move <direction> <distance> - Move rover (e.g. forward 5)\n"
        "/photo <camera> - Take a photo (mastcam, navcam)\n"
        "/status - Rover telemetry\n"
        "/scan - 360° LIDAR scan\n"
        "/report - Session summary\n"
        "/explore - Start autonomous exploration\n"
        "/stop - Emergency stop\n\n"
        "Or just send a text or voice message with natural language!"
    )


async def move_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _allowed(update.effective_user.id):
        await update.message.reply_text("Not authorized.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /move forward | backward | left | right")
        return
    direction = (context.args[0] or "").strip().lower()
    linear, angular, duration = 0.0, 0.0, 2.0
    if direction == "forward":
        linear, angular = 0.3, 0.0
    elif direction == "backward":
        linear, angular = -0.3, 0.0
    elif direction == "left":
        linear, angular = 0.0, 0.3
    elif direction == "right":
        linear, angular = 0.0, -0.3
    else:
        await update.message.reply_text("Unknown direction. Use: forward, backward, left, right")
        return
    result = await _bridge_drive(linear, angular, duration)
    if result is not None:
        await update.message.reply_text(f"Moving {direction}.")
    else:
        await update.message.reply_text("Bridge unreachable. Is the sensor bridge running?")


async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _allowed(update.effective_user.id):
        await update.message.reply_text("Not authorized.")
        return
    data = await _bridge_status()
    if data is None:
        await update.message.reply_text("Bridge unreachable.")
        return
    pos = data.get("position", {})
    orient = data.get("orientation", {})
    vel = data.get("velocity", {})
    hazard = data.get("hazard_detected", False)
    sim = data.get("sim_connected", False)
    uptime = data.get("uptime_seconds", 0)
    msg = (
        f"Position: x={pos.get('x', 0):.2f} y={pos.get('y', 0):.2f} z={pos.get('z', 0):.2f}\n"
        f"Orientation: roll={orient.get('roll', 0):.2f} pitch={orient.get('pitch', 0):.2f} yaw={orient.get('yaw', 0):.2f}\n"
        f"Velocity: linear={vel.get('linear', 0):.2f} angular={vel.get('angular', 0):.2f}\n"
        f"Hazard: {'yes' if hazard else 'no'}\n"
        f"Sim connected: {'yes' if sim else 'no'}\n"
        f"Uptime: {uptime}s"
    )
    await update.message.reply_text(msg)


async def explore_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _allowed(update.effective_user.id):
        await update.message.reply_text("Not authorized.")
        return
    response, photo_path, photo_caption = await _api_command("Explore the area autonomously.", update.effective_user.id)
    if response:
        await _send_api_response(update, response, photo_path, photo_caption)
    else:
        await update.message.reply_text(
            "Natural language / explore not configured. Start the API, or use Hermes Gateway (Option A)."
        )


async def photo_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _allowed(update.effective_user.id):
        await update.message.reply_text("Not authorized.")
        return
    camera = (context.args[0] or "mastcam").strip().lower()
    if camera not in ("mastcam", "navcam", "hazcam_front", "hazcam_rear"):
        camera = "mastcam"
    response, photo_path, photo_caption = await _api_command(f"take a photo with {camera}", update.effective_user.id)
    if response:
        await _send_api_response(update, response, photo_path, photo_caption)
    else:
        await update.message.reply_text("API unreachable. Is the server running on port 8000?")


async def scan_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _allowed(update.effective_user.id):
        await update.message.reply_text("Not authorized.")
        return
    response, _, _ = await _api_command("Perform a 360° LIDAR scan and report the clearest direction.", update.effective_user.id)
    if response:
        await _send_api_response(update, response)
    else:
        await update.message.reply_text("API unreachable. Is the server running on port 8000?")


async def stop_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _allowed(update.effective_user.id):
        await update.message.reply_text("Not authorized.")
        return
    await _bridge_drive(0.0, 0.0, 1.0)
    await update.message.reply_text("Stopped.")


async def _api_report_pdf() -> bytes | None:
    """GET API_URL/report/pdf; return PDF bytes or None."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{API_URL}/report/pdf",
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status == 200:
                    return await resp.read()
                return None
    except Exception:
        return None


async def report_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _allowed(update.effective_user.id):
        await update.message.reply_text("Not authorized.")
        return
    pdf_bytes = await _api_report_pdf()
    if pdf_bytes:
        await update.message.reply_document(
            document=io.BytesIO(pdf_bytes),
            filename="mars_rover_report.pdf",
        )
        return
    report = await _api_report()
    if report:
        await _send_api_response(update, report)
    else:
        response, _, _ = await _api_command("Generate a session report for the current session.", update.effective_user.id)
        if response:
            await _send_api_response(update, response)
        else:
            await update.message.reply_text("Report requested; report API not yet configured.")


def _wants_report_pdf(text: str) -> bool:
    """True if the message is asking for the report in PDF form."""
    t = text.lower().strip()
    return "pdf" in t and ("report" in t or "summary" in t)


def _wants_report(text: str) -> bool:
    """True if user is asking for a report in any format."""
    t = text.lower().strip()
    if "report" not in t and "summary" not in t:
        return False
    return any(k in t for k in ("send", "give", "generate", "show", "telegram", "mission"))


async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _allowed(update.effective_user.id):
        await update.message.reply_text("Not authorized.")
        return
    text = (update.message.text or "").strip()
    if not text:
        return
    if _wants_report_pdf(text):
        pdf_bytes = await _api_report_pdf()
        if pdf_bytes:
            await update.message.reply_document(
                document=io.BytesIO(pdf_bytes),
                filename="mars_rover_report.pdf",
            )
            return
        report_text = await _api_report()
        if report_text:
            await _send_api_response(
                update,
                "PDF isn't available from the server right now. Here's the text report:\n\n" + report_text,
            )
            return
    if _wants_report(text):
        await report_cmd(update, context)
        return
    response, photo_path, photo_caption = await _api_command(text, update.effective_user.id)
    if response:
        await _send_api_response(update, response, photo_path, photo_caption)
    else:
        await update.message.reply_text(
            "Natural language not configured. Use /move, /status, /stop, /report, or set up the API / Hermes Gateway."
        )


async def voice_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _allowed(update.effective_user.id):
        await update.message.reply_text("Not authorized.")
        return
    voice = update.message.voice
    if not voice:
        return
    file = await context.bot.get_file(voice.file_id)
    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        await file.download_to_drive(tmp_path)
        text = await _transcribe_via_api(tmp_path)
        if text is None:
            loop = asyncio.get_event_loop()
            text = (await loop.run_in_executor(None, _transcribe_voice_sync, tmp_path)) or ""
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass
        for ext in (".txt",):
            p = Path(tmp_path).with_suffix(ext)
            if p.exists():
                try:
                    p.unlink()
                except Exception:
                    pass
    if not text:
        await update.message.reply_text("Could not transcribe voice. Install whisper CLI: pip install openai-whisper && whisper --help")
        return
    await update.message.reply_text(f"Heard: {text[:500]}")
    response, photo_path, photo_caption = await _api_command(text, update.effective_user.id)
    if response:
        await _send_api_response(update, response, photo_path, photo_caption)
    else:
        await update.message.reply_text("Processed as text; natural language backend not configured. Use /move, /status, etc.")


def main() -> None:
    if not TELEGRAM_BOT_TOKEN:
        raise SystemExit("Set TELEGRAM_BOT_TOKEN in the environment or .env")
    app = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .build()
    )
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("move", move_cmd))
    app.add_handler(CommandHandler("photo", photo_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("scan", scan_cmd))
    app.add_handler(CommandHandler("explore", explore_cmd))
    app.add_handler(CommandHandler("stop", stop_cmd))
    app.add_handler(CommandHandler("report", report_cmd))
    app.add_handler(MessageHandler(filters.VOICE, voice_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

