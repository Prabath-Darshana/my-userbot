def resolve_send_target(entity, reply_to=None):
    """Return a safe send target for Telegram messages.

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
    """Normalize Telethon message fetch results so media replies work for both
    single-message and list-based responses.
    """
    if message_result is None:
        return None

    if isinstance(message_result, list):
        if not message_result:
            return None
        message_result = message_result[0]

    return message_result
