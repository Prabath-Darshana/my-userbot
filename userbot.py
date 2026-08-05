import json
import os
import threading
from datetime import datetime
import pytz
from flask import Flask
from telethon import TelegramClient, events
from telethon.sessions import StringSession

app = Flask(__name__)

@app.route('/')
def home():
    return "Userbot is Live!"

api_id = 35039780
api_hash = '4ec122e3bde00836e5a02223c5a7714d'

session_str = os.environ.get("STRING_SESSION", "")
client = TelegramClient(StringSession(session_str), api_id, api_hash, sequential_updates=True)

RESPONSES = {}
MEDIA_RESPONSES = {}
IGNORED_USERS = set()
REPLIED_USERS = set()
KNOWN_CONTACTS = set()

AFK_MODE = False
AFK_REASON = ""
WORKING_HOURS_ONLY = False
WELCOME_MSG_ENABLED = True  # Default On

async def load_bot_data():
    global RESPONSES, MEDIA_RESPONSES, IGNORED_USERS, WORKING_HOURS_ONLY, WELCOME_MSG_ENABLED
    try:
        async for msg in client.iter_messages('me', search="[USERBOT_DATA_SAVE]"):
            if msg.text and "[USERBOT_DATA_SAVE]" in msg.text:
                json_str = msg.text.split("[USERBOT_DATA_SAVE]")[1].strip()
                data = json.loads(json_str)
                RESPONSES = data.get("responses", {})
                MEDIA_RESPONSES = data.get("media_responses", {})
                IGNORED_USERS = set(data.get("ignored", []))
                WORKING_HOURS_ONLY = data.get("working_hours", False)
                WELCOME_MSG_ENABLED = data.get("welcome_msg", True)
                break
    except Exception as e:
        print(f"Data Load Error: {e}")

async def save_bot_data():
    global RESPONSES, MEDIA_RESPONSES, IGNORED_USERS, WORKING_HOURS_ONLY, WELCOME_MSG_ENABLED
    try:
        data = {
            "responses": RESPONSES,
            "media_responses": MEDIA_RESPONSES,
            "ignored": list(IGNORED_USERS),
            "working_hours": WORKING_HOURS_ONLY,
            "welcome_msg": WELCOME_MSG_ENABLED
        }
        text_to_save = f"[USERBOT_DATA_SAVE]\n{json.dumps(data, ensure_ascii=False)}"
        
        async for msg in client.iter_messages('me', search="[USERBOT_DATA_SAVE]"):
            await msg.delete()
            
        await client.send_message('me', text_to_save)
    except Exception as e:
        print(f"Data Save Error: {e}")

@client.on(events.NewMessage(outgoing=True))
async def command_handler(event):
    global RESPONSES, MEDIA_RESPONSES, IGNORED_USERS, REPLIED_USERS, AFK_MODE, AFK_REASON, WORKING_HOURS_ONLY, WELCOME_MSG_ENABLED
    try:
        raw_text = event.raw_text.strip()
        lines = raw_text.split('\n')
        added_count = 0

        if AFK_MODE and not raw_text.startswith("!afk"):
            AFK_MODE = False
            AFK_REASON = ""
            await client.send_message('me', "🟢 **AFK Mode Turn Off විය.**")

        if raw_text.startswith("!afk"):
            arg = raw_text[4:].strip()
            if arg.lower() == "off":
                AFK_MODE = False
                AFK_REASON = ""
                await event.edit("🟢 **AFK Mode Off කරන ලදී.**")
            elif arg.lower() == "on":
                AFK_MODE = True
                if not AFK_REASON:
                    AFK_REASON = "වැඩක ඉන්නේ."
                await event.edit("🔴 **AFK Mode On කරන ලදී.**")
            else:
                AFK_REASON = arg or "වැඩක ඉන්නේ."
                AFK_MODE = True
                await event.edit(f"🔴 **AFK Mode On විය!**\n හේතුව: `{AFK_REASON}`")
            return

        if raw_text.startswith("!hours"):
            arg = raw_text[6:].strip().lower()
            if arg == "on":
                WORKING_HOURS_ONLY = True
                await save_bot_data()
                await event.edit("⏰ **Working Hours Mode On (උදේ 7:00 - රෑ 1:00) විය.**")
            elif arg == "off":
                WORKING_HOURS_ONLY = False
                await save_bot_data()
                await event.edit("⏰ **Working Hours Mode Off විය.**")
            return

        if raw_text.startswith("!welcome"):
            arg = raw_text[8:].strip().lower()
            if arg == "on":
                WELCOME_MSG_ENABLED = True
                await save_bot_data()
                await event.edit("👋 **Welcome Message ON කරන ලදී.**")
            elif arg == "off":
                WELCOME_MSG_ENABLED = False
                await save_bot_data()
                await event.edit("👋 **Welcome Message OFF කරන ලදී.**")
            return

        if raw_text.startswith("!addmedia ") and event.is_reply:
            word = raw_text[10:].strip().lower()
            reply_msg = await event.get_reply_message()
            if reply_msg and word:
                MEDIA_RESPONSES[word] = reply_msg.id
                await save_bot_data()
                await event.edit(f"🖼️ **Media Auto-Reply එකතු කළා (`{word}`)!**")
            return

        if raw_text.startswith("!delmedia "):
            word = raw_text[10:].strip().lower()
            if word in MEDIA_RESPONSES:
                del MEDIA_RESPONSES[word]
                await save_bot_data()
                await event.edit(f"🗑️ Media Auto-Reply `{word}` **අයින් කළා.**")
            else:
                await event.edit(f"❌ Media Reply `{word}` සොයාගත නොහැකි විය.")
            return

        if raw_text == "!listmedia":
            if not MEDIA_RESPONSES:
                await event.edit("📝 **Media Auto Replies කිසිවක් නැත.**")
                return
            msg = f"🖼️ **Media Auto Replies ({len(MEDIA_RESPONSES)}):**\n\n"
            for w in MEDIA_RESPONSES.keys():
                msg += f"• `{w}` ➔ 🖼️ [Saved Media]\n"
            await event.edit(msg)
            return

        if raw_text.startswith("!gcast "):
            msg_to_send = raw_text[7:].strip()
            await event.edit("📢 **Broadcasting Message...**")
            dialogs = await client.get_dialogs()
            sent_count = 0
            for dialog in dialogs:
                if dialog.is_user and not dialog.entity.bot and dialog.id not in IGNORED_USERS:
                    try:
                        await client.send_message(dialog.id, msg_to_send)
                        sent_count += 1
                    except Exception:
                        pass
            await event.edit(f"✅ **Broadcast Done! Messages {sent_count} කට යැවීය.**")
            return

        if (raw_text in ["!block", "!nobot"]) and event.is_reply:
            reply_msg = await event.get_reply_message()
            user_id = reply_msg.sender_id
            me = await client.get_me()
            if user_id != me.id:
                IGNORED_USERS.add(user_id)
                await save_bot_data()
                await event.edit("✅ **Auto-responses turned off for this contact.**")
            return

        if raw_text == "!unblock" and event.is_reply:
            reply_msg = await event.get_reply_message()
            user_id = reply_msg.sender_id
            if user_id in IGNORED_USERS:
                IGNORED_USERS.remove(user_id)
                await save_bot_data()
                await event.edit("✅ **Saved. Auto-responses re-enabled for this contact.**")
            return

        if raw_text == "!blocklist":
            await event.edit(f"🚫 **Block කර ඇති ගණන:** `{len(IGNORED_USERS)}`")
            return

        for line in lines:
            line = line.strip()
            if line.startswith("!add "):
                try:
                    content = line[5:]
                    if "=" in content:
                        word, reply = content.split("=", 1)
                        word, reply = word.strip().lower(), reply.strip()
                        if word:
                            RESPONSES[word] = reply
                            added_count += 1
                except Exception:
                    pass

        if added_count > 0:
            await save_bot_data()
            await event.edit(f"✅ **Auto Replies {added_count}ක් එකතු කළා!**")
            return

        if raw_text.startswith("!del "):
            word = raw_text[5:].strip().lower()
            RESPONSES.pop(word, None)
            MEDIA_RESPONSES.pop(word, None)
            await save_bot_data()
            await event.edit(f"🗑️ `{word}` **අයින් කළා.**")

        elif raw_text == "!clear":
            RESPONSES.clear()
            MEDIA_RESPONSES.clear()
            await save_bot_data()
            await event.edit("🗑️ **සියලුම Auto Replies මකා දැමීය!**")

        elif raw_text == "!list":
            msg = f"📝 **Auto Replies ({len(RESPONSES) + len(MEDIA_RESPONSES)}):**\n\n"
            for w, r in RESPONSES.items():
                msg += f"• `{w}` ➔ {r}\n"
            for w in MEDIA_RESPONSES.keys():
                msg += f"• `{w}` ➔ 🖼️ [Media Response]\n"
            await event.edit(msg if (RESPONSES or MEDIA_RESPONSES) else "📝 **ලැයිස්තුව හිස්ය.**")

        elif raw_text == "!reset":
            REPLIED_USERS.clear()
            KNOWN_CONTACTS.clear()
            await event.edit("🔄 **History Reset කළා!**")

    except Exception:
        pass

@client.on(events.NewMessage(incoming=True, func=lambda e: e.is_private))
async def reply_handler(event):
    global REPLIED_USERS, IGNORED_USERS, AFK_MODE, AFK_REASON, WORKING_HOURS_ONLY, WELCOME_MSG_ENABLED, KNOWN_CONTACTS
    try:
        sender = await event.get_sender()
        user_id = event.sender_id

        if not sender or getattr(sender, 'bot', False):
            return

        if user_id in IGNORED_USERS:
            return

        if WORKING_HOURS_ONLY:
            tz = pytz.timezone('Asia/Colombo')
            current_hour = datetime.now(tz).hour
            if 1 <= current_hour < 7:
                return

        # 1. AFK Mode Check
        if AFK_MODE:
            await event.reply(f"🤖 {AFK_REASON}")
            return

        # 2. Direct Welcome Message Check (100% Reliable Check)
        if WELCOME_MSG_ENABLED and user_id not in KNOWN_CONTACTS:
            is_contact = getattr(sender, 'contact', False)
            if not is_contact:
                await event.reply("💌 Hey! 💖 Thanks for your message. I'll reply soon. 😊")
                KNOWN_CONTACTS.add(user_id)
                return

        incoming_raw = event.raw_text.strip().lower()
        replied = False

        # 3. Custom Media Reply Check
        if incoming_raw in MEDIA_RESPONSES:
            msg_id = MEDIA_RESPONSES[incoming_raw]
            saved_msg = await client.get_messages('me', ids=msg_id)
            if saved_msg:
                await event.reply(saved_msg)
                replied = True

        # 4. Custom Text Reply Check
        if not replied:
            for word, reply in RESPONSES.items():
                target_word = word.strip().lower()
                if target_word and (target_word == incoming_raw or target_word in incoming_raw.split()):
                    await event.reply(reply)
                    replied = True
                    break

        # 5. Default Reply
        if not replied and user_id not in REPLIED_USERS:
            await event.reply("මං පොඩි වැඩක ඉන්නේ. 💻 මේක Auto Reply එකක්, ආපු ගමන් මැසේජ් එකක් දාන්නම් හොඳේ! ✨")
            REPLIED_USERS.add(user_id)

    except Exception as e:
        print(f"Reply Error: {e}")

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

if __name__ == "__main__":
    t = threading.Thread(target=run_flask)
    t.daemon = True
    t.start()
    
    async def start_bot():
        await client.start()
        await load_bot_data()
        try:
            await client.send_message('me', "🚀 **Userbot Fixed & Ready for Welcome Messages!**")
        except Exception:
            pass
        await client.run_until_disconnected()

    client.loop.run_until_complete(start_bot())
