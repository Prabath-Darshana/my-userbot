import unittest

from bot_utils import (
    can_send_ai_reply,
    extract_media_message,
    extract_youtube_url,
    normalize_bot_state,
    parse_bulk_replies,
    parse_size_limit_mb,
    resolve_send_target,
    resolve_telegram_config,
)


class ResolveSendTargetTests(unittest.TestCase):
    def test_normalize_bot_state_uses_defaults_for_missing_values(self):
        defaults = {
            "responses": {},
            "media_responses": {},
            "ignored": [],
            "known_contacts": [],
            "bot_blocked_users": [],
            "working_hours": False,
            "start_hour": 1,
            "end_hour": 7,
            "welcome_msg": True,
            "ai_reply": True,
            "afk_mode": False,
            "afk_reason": "default",
            "todo_list": [],
        }
        state = normalize_bot_state({"responses": {"hi": "hello"}}, defaults)
        self.assertEqual(state["responses"], {"hi": "hello"})
        self.assertFalse(state["working_hours"])
        self.assertEqual(state["start_hour"], 1)
        self.assertEqual(state["afk_reason"], "default")

    def test_can_send_ai_reply_only_after_cooldown(self):
        replied_users = {7: 100}
        self.assertFalse(can_send_ai_reply(7, 150, replied_users, 60))
        self.assertTrue(can_send_ai_reply(8, 150, replied_users, 60))

    def test_extract_media_message_handles_single_result(self):
        message = object()
        self.assertIs(extract_media_message(message), message)

    def test_extract_media_message_handles_list_result(self):
        message = object()
        self.assertIs(extract_media_message([message]), message)

    def test_extract_media_message_handles_empty_list(self):
        self.assertIsNone(extract_media_message([]))

    def test_resolve_telegram_config_uses_defaults_for_invalid_values(self):
        api_id, api_hash = resolve_telegram_config(123, "hash", {"API_ID": "bad", "API_HASH": ""})
        self.assertEqual(api_id, 123)
        self.assertEqual(api_hash, "hash")

    def test_parse_size_limit_mb_uses_default_for_invalid_values(self):
        self.assertEqual(parse_size_limit_mb("0"), 100)
        self.assertEqual(parse_size_limit_mb("50"), 50)

    def test_parse_bulk_replies_handles_multiple_entries(self):
        text = "gn=Good Night..! 🌙\ngm=Good Morning..! ☀️\ntc=Take Care!"
        self.assertEqual(
            parse_bulk_replies(text),
            {"gn": "Good Night..! 🌙", "gm": "Good Morning..! ☀️", "tc": "Take Care!"},
        )

    def test_extract_youtube_url_parses_common_links(self):
        self.assertEqual(extract_youtube_url("!ytmp3 https://www.youtube.com/watch?v=abc"), "https://www.youtube.com/watch?v=abc")
        self.assertEqual(extract_youtube_url("!ytmp3 https://youtu.be/abc123"), "https://youtu.be/abc123")
        self.assertIsNone(extract_youtube_url("not a url"))

    def test_prefers_reply_method_when_available(self):
        class ReplyTarget:
            def __init__(self):
                self.chat_id = 123

            async def reply(self, text):
                return text

        target = ReplyTarget()
        self.assertEqual(resolve_send_target("entity", reply_to=target), ("reply", target))

    def test_falls_back_to_chat_id_when_reply_is_missing(self):
        class ChatTarget:
            def __init__(self):
                self.chat_id = 456

        target = ChatTarget()
        self.assertEqual(resolve_send_target("entity", reply_to=target), ("chat", 456))

    def test_falls_back_to_entity_when_no_chat_id_exists(self):
        self.assertEqual(resolve_send_target("entity"), ("entity", "entity"))


if __name__ == "__main__":
    unittest.main()
