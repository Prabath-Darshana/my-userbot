import logging
import os
import re
from typing import Any, Dict, Mapping, Optional, Tuple

logger = logging.getLogger(__name__)


def resolve_send_target(entity: Any, reply_to: Optional[Any] = None) -> Tuple[str, Any]:
    """Choose a safe Telegram message send target.

    Prefer replying to `reply_to` when it appears to be a reply-capable object.
    Fall back to chat id or the original entity.
    """
    if reply_to is not None:
        try:
            if hasattr(reply_to, "reply") and callable(getattr(reply_to, "reply")):
                return "reply", reply_to

            chat_id = getattr(reply_to, "chat_id", None)
            if chat_id is not None:
                return "chat", chat_id
        except Exception:
            logger.debug("reply_to inspection failed", exc_info=True)

    chat_id = getattr(entity, "chat_id", None)
    if chat_id is not None:
        return "chat", chat_id

    return "entity", entity


def extract_media_message(message_result: Any) -> Optional[Any]:
    """Normalize a Telethon message or list/tuple of messages to a single message or None."""
    if message_result is None:
        return None

    if isinstance(message_result, (list, tuple)):
        if not message_result:
            return None
        message_result = message_result[0]

    return message_result


def normalize_bot_state(data: Any, defaults: Mapping[str, Any]) -> Dict[str, Any]:
    """Ensure persisted bot state has safe shapes and defaults after restart."""
    if not isinstance(data, dict):
        data = {}

    normalized: Dict[str, Any] = {}
    for key, default_value in defaults.items():
        value = data.get(key, default_value)
        if key in {"responses", "media_responses"}:
            normalized[key] = value if isinstance(value, dict) else {}
        elif key in {"ignored", "known_contacts", "bot_blocked_users", "todo_list"}:
            normalized[key] = value if isinstance(value, list) else []
        elif key in {"working_hours", "welcome_msg", "ai_reply", "afk_mode"}:
            normalized[key] = bool(value)
        elif key in {"start_hour", "end_hour"}:
            try:
                normalized[key] = int(value)
            except (TypeError, ValueError):
                normalized[key] = default_value
        else:
            normalized[key] = value if value is not None else default_value

    return normalized


def can_send_ai_reply(user_id: Any, current_time: float, replied_users: Mapping[Any, float], cooldown_seconds: float) -> bool:
    """Return True if user may receive an AI auto-reply based on a cooldown."""
    try:
        last_replied = float(replied_users.get(user_id, 0))
    except Exception:
        last_replied = 0.0
    try:
        return (float(current_time) - last_replied) > float(cooldown_seconds)
    except Exception:
        logger.debug("Invalid time values provided to can_send_ai_reply", exc_info=True)
        return True


def resolve_telegram_config(default_api_id: int, default_api_hash: str, env: Optional[Mapping[str, str]] = None) -> Tuple[int, str]:
    """Load Telegram API credentials from environment mapping, with safe defaults."""
    env = os.environ if env is None else env
    api_id_value = env.get("API_ID", str(default_api_id)) if isinstance(env, Mapping) else str(default_api_id)
    api_hash_value = env.get("API_HASH", default_api_hash) if isinstance(env, Mapping) else default_api_hash

    try:
        api_id = int(api_id_value)
    except (TypeError, ValueError):
        api_id = default_api_id

    if not isinstance(api_hash_value, str) or not api_hash_value.strip():
        api_hash = default_api_hash
    else:
        api_hash = api_hash_value

    return api_id, api_hash


def parse_size_limit_mb(value: Any, default_mb: int = 100) -> int:
    """Parse a size limit (in MB) from env-like values, returning a positive int."""
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        return default_mb
    return parsed if parsed > 0 else default_mb


def extract_youtube_url(text: Optional[str]) -> Optional[str]:
    """Return the first YouTube URL found in `text`, or None."""
    if not text:
        return None
    match = re.search(r'https?://(?:www\.)?(?:youtube\.com|youtu\.be)[^\s>]+', text, re.IGNORECASE)
    if not match:
        return None
    try:
        return match.group(0).rstrip('>')
    except Exception:
        logger.debug("Failed to extract youtube url from text", exc_info=True)
        return None


def parse_bulk_replies(text: Optional[str]) -> Dict[str, str]:
    """Parse a multi-line bulk reply block into a dict of key -> reply pairs."""
    if not text:
        return {}

    replies: Dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or '=' not in stripped:
            continue
        key, value = stripped.split('=', 1)
        key = key.strip().lower()
        value = value.strip()
        if key and value:
            replies[key] = value
    return replies
