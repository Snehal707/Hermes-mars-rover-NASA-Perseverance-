"""Send Message Tool -- cross-channel messaging via platform APIs.

Sends a message to a user or channel on any connected messaging platform
(Telegram, Discord, Slack). Supports listing available targets and resolving
human-friendly channel names to IDs. Works in both CLI and gateway contexts.
"""

import json
import logging
import os
import re
import io
from pathlib import Path

logger = logging.getLogger(__name__)


def _media_debug_enabled() -> bool:
    return os.getenv("HERMES_MEDIA_DEBUG", "").strip().lower() in {"1", "true", "yes", "on"}


def _media_debug(msg: str, *args, **kwargs) -> None:
    if _media_debug_enabled():
        logger.warning("[media-debug/send_message] " + msg, *args, **kwargs)


SEND_MESSAGE_SCHEMA = {
    "name": "send_message",
    "description": (
        "Send a message to a connected messaging platform, or list available targets.\n\n"
        "IMPORTANT: When the user asks to send to a specific channel or person "
        "(not just a bare platform name), call send_message(action='list') FIRST to see "
        "available targets, then send to the correct one.\n"
        "If the user just says a platform name like 'send to telegram', send directly "
        "to the home channel without listing first."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["send", "list"],
                "description": "Action to perform. 'send' (default) sends a message. 'list' returns all available channels/contacts across connected platforms."
            },
            "target": {
                "type": "string",
                "description": "Delivery target. Format: 'platform' (uses home channel), 'platform:#channel-name', or 'platform:chat_id'. Examples: 'telegram', 'discord:#bot-home', 'slack:#engineering'"
            },
            "message": {
                "type": "string",
                "description": "The message text to send"
            }
        },
        "required": []
    }
}


def send_message_tool(args, **kw):
    """Handle cross-channel send_message tool calls."""
    action = args.get("action", "send")

    if action == "list":
        return _handle_list()

    return _handle_send(args)


def _handle_list():
    """Return formatted list of available messaging targets."""
    try:
        from gateway.channel_directory import format_directory_for_display
        return json.dumps({"targets": format_directory_for_display()})
    except Exception as e:
        return json.dumps({"error": f"Failed to load channel directory: {e}"})


def _handle_send(args):
    """Send a message to a platform target."""
    target = args.get("target", "")
    message = args.get("message", "")
    if not target or not message:
        return json.dumps({"error": "Both 'target' and 'message' are required when action='send'"})
    media_files, clean_message = _extract_media_tags(message)
    _media_debug(
        "handle_send target=%s media_count=%d clean_len=%d",
        target,
        len(media_files),
        len(clean_message or ""),
    )
    if not clean_message and not media_files:
        return json.dumps({"error": "Message is empty after removing MEDIA tags"})

    parts = target.split(":", 1)
    platform_name = parts[0].strip().lower()
    chat_id = parts[1].strip() if len(parts) > 1 else None
    _media_debug("parsed target platform=%s chat_id=%s", platform_name, chat_id or "<home>")

    # Resolve human-friendly channel names to numeric IDs
    if chat_id and not chat_id.lstrip("-").isdigit():
        try:
            from gateway.channel_directory import resolve_channel_name
            resolved = resolve_channel_name(platform_name, chat_id)
            if resolved:
                chat_id = resolved
            else:
                return json.dumps({
                    "error": f"Could not resolve '{chat_id}' on {platform_name}. "
                    f"Use send_message(action='list') to see available targets."
                })
        except Exception:
            return json.dumps({
                "error": f"Could not resolve '{chat_id}' on {platform_name}. "
                f"Try using a numeric channel ID instead."
            })

    from tools.interrupt import is_interrupted
    if is_interrupted():
        return json.dumps({"error": "Interrupted"})

    try:
        from gateway.config import load_gateway_config, Platform
        config = load_gateway_config()
    except Exception as e:
        return json.dumps({"error": f"Failed to load gateway config: {e}"})

    platform_map = {
        "telegram": Platform.TELEGRAM,
        "discord": Platform.DISCORD,
        "slack": Platform.SLACK,
        "whatsapp": Platform.WHATSAPP,
    }
    platform = platform_map.get(platform_name)
    if not platform:
        avail = ", ".join(platform_map.keys())
        return json.dumps({"error": f"Unknown platform: {platform_name}. Available: {avail}"})

    pconfig = config.platforms.get(platform)
    if not pconfig or not pconfig.enabled:
        return json.dumps({"error": f"Platform '{platform_name}' is not configured. Set up credentials in ~/.hermes/gateway.json or environment variables."})

    used_home_channel = False
    if not chat_id:
        home = config.get_home_channel(platform)
        if home:
            chat_id = home.chat_id
            used_home_channel = True
        else:
            return json.dumps({
                "error": f"No home channel set for {platform_name} to determine where to send the message. "
                f"Either specify a channel directly with '{platform_name}:CHANNEL_NAME', "
                f"or set a home channel via: hermes config set {platform_name.upper()}_HOME_CHANNEL <channel_id>"
            })

    try:
        from model_tools import _run_async
        result = _run_async(
            _send_to_platform(
                platform=platform,
                pconfig=pconfig,
                chat_id=chat_id,
                message=clean_message,
                media_files=media_files,
            )
        )
        if used_home_channel and isinstance(result, dict) and result.get("success"):
            result["note"] = f"Sent to {platform_name} home channel (chat_id: {chat_id})"

        # Mirror the sent message into the target's gateway session
        if isinstance(result, dict) and result.get("success"):
            try:
                from gateway.mirror import mirror_to_session
                source_label = os.getenv("HERMES_SESSION_PLATFORM", "cli")
                if mirror_to_session(platform_name, chat_id, message, source_label=source_label):
                    result["mirrored"] = True
            except Exception:
                pass

        return json.dumps(result)
    except Exception as e:
        return json.dumps({"error": f"Send failed: {e}"})


async def _send_to_platform(platform, pconfig, chat_id, message, media_files=None):
    """Route a message to the appropriate platform sender."""
    from gateway.config import Platform
    media_files = media_files or []
    if platform == Platform.TELEGRAM:
        return await _send_telegram(pconfig.token, chat_id, message, media_files)
    elif platform == Platform.DISCORD:
        return await _send_discord(pconfig.token, chat_id, message, media_files)
    elif platform == Platform.SLACK:
        return await _send_slack(pconfig.token, chat_id, message, media_files)
    return {"error": f"Direct sending not yet implemented for {platform.value}"}


async def _send_telegram(token, chat_id, message, media_files=None):
    """Send via Telegram Bot API (one-shot, no polling needed)."""
    media_files = media_files or []
    try:
        from telegram import Bot

        bot = Bot(token=token)
        sent_ids = []
        errors = []
        media_requested = len(media_files)
        media_sent = 0
        _media_debug(
            "_send_telegram chat_id=%s msg_len=%d media_requested=%d",
            chat_id,
            len(message or ""),
            media_requested,
        )

        if message:
            msg = await bot.send_message(chat_id=int(chat_id), text=message)
            sent_ids.append(str(msg.message_id))
            _media_debug("sent text message_id=%s", msg.message_id)

        audio_exts = {".ogg", ".opus", ".mp3", ".wav", ".m4a"}
        video_exts = {".mp4", ".mov", ".avi", ".mkv", ".3gp"}
        image_exts = {".jpg", ".jpeg", ".png", ".webp", ".gif"}

        for idx, (media_path, _is_voice) in enumerate(media_files, start=1):
            ext = Path(media_path).suffix.lower()
            exists = os.path.exists(media_path)
            _media_debug("media[%d] path=%s ext=%s exists=%s", idx, media_path, ext, exists)
            if not os.path.exists(media_path):
                # PDF fallback: if ephemeral /tmp path disappeared, fetch report from API.
                if ext == ".pdf":
                    _media_debug("media[%d] missing PDF, trying /report/pdf fallback", idx)
                    pdf_bytes = await _fetch_report_pdf_bytes()
                    if pdf_bytes:
                        _media_debug("media[%d] fallback bytes=%d", idx, len(pdf_bytes))
                        try:
                            sent = await bot.send_document(
                                chat_id=int(chat_id),
                                document=io.BytesIO(pdf_bytes),
                                filename=os.path.basename(media_path) or "mars_rover_report.pdf",
                            )
                            sent_ids.append(str(sent.message_id))
                            media_sent += 1
                            _media_debug("media[%d] fallback send_document message_id=%s", idx, sent.message_id)
                            continue
                        except Exception as pdf_err:
                            _media_debug("media[%d] fallback send failed: %s", idx, pdf_err)
                            errors.append(f"{media_path}: report/pdf fallback failed: {pdf_err}")
                errors.append(f"File not found: {media_path}")
                continue
            try:
                with open(media_path, "rb") as file_handle:
                    if ext in audio_exts:
                        if ext in {".ogg", ".opus"}:
                            sent = await bot.send_voice(chat_id=int(chat_id), voice=file_handle)
                            route = "voice"
                        else:
                            sent = await bot.send_audio(chat_id=int(chat_id), audio=file_handle)
                            route = "audio"
                    elif ext in video_exts:
                        sent = await bot.send_video(chat_id=int(chat_id), video=file_handle)
                        route = "video"
                    elif ext in image_exts:
                        sent = await bot.send_photo(chat_id=int(chat_id), photo=file_handle)
                        route = "photo"
                    else:
                        sent = await bot.send_document(
                            chat_id=int(chat_id),
                            document=file_handle,
                            filename=os.path.basename(media_path),
                        )
                        route = "document"
                sent_ids.append(str(sent.message_id))
                media_sent += 1
                _media_debug("media[%d] sent route=%s message_id=%s", idx, route, sent.message_id)
            except Exception as media_err:
                _media_debug("media[%d] send failed: %s", idx, media_err)
                errors.append(f"{media_path}: {media_err}")

        success = bool(sent_ids)
        # If caller requested attachments, require all media uploads to succeed.
        if media_requested > 0 and media_sent < media_requested:
            success = False

        result = {
            "success": success,
            "platform": "telegram",
            "chat_id": chat_id,
            "message_ids": sent_ids,
            "media_requested": media_requested,
            "media_sent": media_sent,
        }
        if errors:
            result["warnings"] = errors
            if not success:
                result["error"] = "One or more media attachments failed to send."
        _media_debug(
            "_send_telegram done success=%s sent_ids=%d media_sent=%d/%d warnings=%d",
            success,
            len(sent_ids),
            media_sent,
            media_requested,
            len(errors),
        )
        return result
    except ImportError:
        return {"error": "python-telegram-bot not installed. Run: pip install python-telegram-bot"}
    except Exception as e:
        return {"error": f"Telegram send failed: {e}"}


async def _send_discord(token, chat_id, message, media_files=None):
    """Send via Discord REST API (no websocket client needed)."""
    media_files = media_files or []
    try:
        import aiohttp
    except ImportError:
        return {"error": "aiohttp not installed. Run: pip install aiohttp"}
    try:
        url = f"https://discord.com/api/v10/channels/{chat_id}/messages"
        headers = {"Authorization": f"Bot {token}", "Content-Type": "application/json"}
        chunks = [message[i:i+2000] for i in range(0, len(message), 2000)] if message else []
        message_ids = []
        async with aiohttp.ClientSession() as session:
            for chunk in chunks:
                async with session.post(url, headers=headers, json={"content": chunk}) as resp:
                    if resp.status not in (200, 201):
                        body = await resp.text()
                        return {"error": f"Discord API error ({resp.status}): {body}"}
                    data = await resp.json()
                    message_ids.append(data.get("id"))
        result = {"success": True, "platform": "discord", "chat_id": chat_id, "message_ids": message_ids}
        if media_files:
            result["warnings"] = ["MEDIA attachments are currently supported for Telegram in send_message."]
        return result
    except Exception as e:
        return {"error": f"Discord send failed: {e}"}


async def _send_slack(token, chat_id, message, media_files=None):
    """Send via Slack Web API."""
    media_files = media_files or []
    try:
        import aiohttp
    except ImportError:
        return {"error": "aiohttp not installed. Run: pip install aiohttp"}
    try:
        url = "https://slack.com/api/chat.postMessage"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        message_id = None
        if message:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json={"channel": chat_id, "text": message}) as resp:
                    data = await resp.json()
                    if not data.get("ok"):
                        return {"error": f"Slack API error: {data.get('error', 'unknown')}"}
                    message_id = data.get("ts")
        result = {"success": True, "platform": "slack", "chat_id": chat_id, "message_id": message_id}
        if media_files:
            result["warnings"] = ["MEDIA attachments are currently supported for Telegram in send_message."]
        return result
    except Exception as e:
        return {"error": f"Slack send failed: {e}"}


def _check_send_message():
    """Gate send_message on gateway running (always available on messaging platforms)."""
    platform = os.getenv("HERMES_SESSION_PLATFORM", "")
    if platform and platform != "local":
        return True
    try:
        from gateway.status import is_gateway_running
        return is_gateway_running()
    except Exception:
        return False


def _extract_media_tags(content: str):
    """Extract MEDIA:<path> tags and [[audio_as_voice]] directive from text."""
    has_voice_tag = "[[audio_as_voice]]" in content
    cleaned = content.replace("[[audio_as_voice]]", "")

    media = []
    media_pattern = r'(?i)\bMEDIA\s*:\s*(?:"([^"]+)"|\'([^\']+)\'|([^\s\n\r]+))'
    for match in re.finditer(media_pattern, content):
        path = (match.group(1) or match.group(2) or match.group(3) or "").strip()
        path = path.strip("`").rstrip('",}])')
        if path:
            media.append((path, has_voice_tag))

    if media:
        cleaned = re.sub(media_pattern, "", cleaned)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    _media_debug("extract_media_tags found=%d paths=%s", len(media), [p for p, _ in media])

    return media, cleaned


async def _fetch_report_pdf_bytes():
    """Best-effort fallback to API /report/pdf when MEDIA PDF path is missing."""
    api_url = os.getenv("API_URL", "http://127.0.0.1:8000").rstrip("/")
    _media_debug("fetch_report_pdf_bytes url=%s/report/pdf", api_url)
    try:
        import aiohttp
    except ImportError:
        _media_debug("fetch_report_pdf_bytes aiohttp not installed")
        return None
    try:
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{api_url}/report/pdf", timeout=timeout) as resp:
                _media_debug("fetch_report_pdf_bytes status=%s", resp.status)
                if resp.status == 200:
                    return await resp.read()
    except Exception:
        _media_debug("fetch_report_pdf_bytes request failed", exc_info=True)
        return None
    return None


# --- Registry ---
from tools.registry import registry

registry.register(
    name="send_message",
    toolset="messaging",
    schema=SEND_MESSAGE_SCHEMA,
    handler=send_message_tool,
    check_fn=_check_send_message,
)
