import unittest

from bot_utils import resolve_send_target


class ResolveSendTargetTests(unittest.TestCase):
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
