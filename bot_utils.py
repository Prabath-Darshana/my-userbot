import os
import re


def resolve_send_target(entity, reply_to=None):
    """Telegram message send target එක safe way එකින් තෝරාගන්න.

    When a reply target is available, prefer it. If the object cannot be used
    for a reply, fall back to its chat id or the original entity.
    """
    if reply_to is not None:
        if hasattr(reply_to, "reply") and callable(getattr(reply_to, "reply")):
            return "reply", reply_to

        chat_id = getattr(reply_to, "chat_id", None)
        if chat_id is not None:
            return "chat", chat_id

    chat_id = getattr(entity, "chat_id", None)
    if chat_id is not None:
        return "chat", chat_id

    return "entity", entity


def extract_media_message(message_result):
    """Telethon එකෙන් ආවා නම් single message හෝ list එකක් වුවත් media reply එකට
    නිවැරදි format එකට convert කරන helper.
    """
    if message_result is None:
        return None

    if isinstance(message_result, list):
        if not message_result:
            return None
        message_result = message_result[0]

    return message_result


def normalize_bot_state(data, defaults):
    """Restart එකකින් පසුව data නැති වුනා면 safe defaults භාවිතා කර bot state normalize කරයි."""
    if not isinstance(data, dict):
        data = {}

    normalized = {}
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


def can_send_ai_reply(user_id, current_time, replied_users, cooldown_seconds):
    """User එකකට AI auto-reply යවන්න පුළුවන් ද නැද්ද කියලා cooldown basedව පරීක්ෂා කරයි."""
    last_replied = replied_users.get(user_id, 0)
    return (current_time - last_replied) > cooldown_seconds


def resolve_telegram_config(default_api_id, default_api_hash, env=None):
    """Environment variables වලින් Telegram credentials ගෙන එන්න. වැරදි/blank values නම් defaults use කරයි."""
    env = os.environ if env is None else env
    api_id_value = env.get("API_ID", default_api_id)
    api_hash_value = env.get("API_HASH", default_api_hash)

    try:
        api_id = int(api_id_value)
    except (TypeError, ValueError):
        api_id = default_api_id

    if not isinstance(api_hash_value, str) or not api_hash_value.strip():
        api_hash = default_api_hash
    else:
        api_hash = api_hash_value

    return api_id, api_hash


def parse_size_limit_mb(value, default_mb=100):
    """Download size limit env var එක safe way එකින් parse කරයි."""
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        return default_mb
    return parsed if parsed > 0 else default_mb


def extract_youtube_url(text):
    """Message එකෙන් YouTube URL එකක් identify කරගන්න."""
    if not text:
        return None
    match = re.search(r'https?://(?:www\.)?(?:youtube\.com|youtu\.be)[^\s>]+', text, re.IGNORECASE)
    if not match:
        return None
    return match.group(0).rstrip('>')
