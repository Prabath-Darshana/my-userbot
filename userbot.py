import json
import os
import threading
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
IGNORED_USERS = set()
REPLIED_USERS = set()

# Saved Messages වලින් Data Auto Read/Write කිරීමේ Functions
async def load_bot_data():
    global RESPONSES, IGNORED_USERS
    try:
        async for msg in client.iter_messages('me', search="[USERBOT_DATA_SAVE]"):
            if msg.text and "[USERBOT_DATA_SAVE]" in msg.text:
                json_str = msg.text.split("[USERBOT_DATA_SAVE]")[1].strip()
                data = json.loads(json_str)
                RESPONSES = data.get("responses", {})
                IGNORED_USERS = set(data.get("ignored", []))
                print("Data Loaded Successfully from Saved Messages!")
                break
    except Exception as e:
        print(f"Data Load Error: {e}")

async def save_bot_data():
    global RESPONSES, IGNORED_USERS
    try:
        data = {
            "responses": RESPONSES,
            "ignored": list(IGNORED_USERS)
        }
        text_to_save = f"[USERBOT_DATA_SAVE]\n{json.dumps(data, ensure_ascii=False)}"
        
        # පරණ Save Message එක Delete කර අලුත් එකක් යැවීම
        async for msg in client.iter_messages('me', search="[USERBOT_DATA_SAVE]"):
            await msg.delete()
            
        await client.send_message('me', text_to_save)
    except Exception as e:
        print(f"Data Save Error: {e}")

# 1. Commands Handler
@client.on(events.NewMessage(outgoing=True))
async def command_handler(event):
    global RESPONSES, IGNORED_USERS, REPLIED_USERS
    try:
        raw_text = event.raw_text.strip()
        lines = raw_text.split('\n')
        added_count = 0

        # !block / !nobot
        if (raw_text in ["!block", "!nobot"]) and event.is_reply:
            reply_msg = await event.get_reply_message()
            user_id = reply_msg.sender_id
            
            me = await client.get_me()
            if user_id == me.id:
                await event.edit("❌ **ඔබගේම මැසේජ් එකකට Block කළ නොහැක. අනිත් කෙනාගේ මැසේජ් එකකට Reply කරන්න!**")
                return

            IGNORED_USERS.add(user_id)
            await save_bot_data()
            await event.edit("✅ **Saved. Auto-responses turned off for this contact.**")
            return

        # !unblock
        if raw_text == "!unblock" and event.is_reply:
            reply_msg = await event.get_reply_message()
            user_id = reply_msg.sender_id
            if user_id in IGNORED_USERS:
                IGNORED_USERS.remove(user_id)
                await save_bot_data()
                await event.edit("✅ **Saved. Auto-responses re-enabled for this contact.**")
            else:
                await event.edit("❌ **මෙම පරිශීලකයා Block ලැයිස්තුවේ නැත.**")
            return

        # !blocklist
        if raw_text == "!blocklist":
            await event.edit(f"🚫 **Auto-Reply Off කර ඇති ගණන:** `{len(IGNORED_USERS)}`")
            return

        # !clearblock
        if raw_text == "!clearblock":
            IGNORED_USERS.clear()
            await save_bot_data()
            await event.edit("🧹 **Block List එක Reset කරන ලදී!**")
            return

        # !add Command
        for line in lines:
            line = line.strip()
            if line.startswith("!add "):
                try:
                    content = line[5:]
                    if "=" in content:
                        word, reply = content.split("=", 1)
                        word = word.strip().lower()
                        reply = reply.strip()
                        if word:
                            RESPONSES[word] = reply
                            added_count += 1
                except Exception:
                    pass

        if added_count > 0:
            await save_bot_data()
            await event.edit(f"✅ **Auto Replies එකතු කළා!**")
            return

        # !del Command
        if raw_text.startswith("!del "):
            word = raw_text[5:].strip().lower()
            if word in RESPONSES:
                del RESPONSES[word]
                save_bot_data()
                await event.edit(f"🗑️ `{word}` **අයින් කළා.**")
            else:
                await event.edit(f"❌ `{word}` සොයාගත නොහැකි විය.")

        # !clear
        elif raw_text == "!clear":
            RESPONSES = {}
            await save_bot_data()
            await event.edit("🗑️ **සියලුම Auto Replies මකා දමන ලදී!**")

        # !list
        elif raw_text == "!list":
            if not RESPONSES:
                await event.edit("📝 **ලැයිස්තුව හිස්ය.**")
                return
            msg = f"📝 **දැනට ඇති Auto Replies ({len(RESPONSES)}):**\n\n"
            for w, r in RESPONSES.items():
                msg += f"• `{w}` ➔ {r}\n"
            await event.edit(msg)

        # !reset
        elif raw_text == "!reset":
            REPLIED_USERS.clear()
            await event.edit("🔄 **Auto-Reply History එක Reset කළා!**")
    except Exception:
        pass

# 2. Auto Reply Handler
@client.on(events.NewMessage(incoming=True, func=lambda e: e.is_private))
async def reply_handler(event):
    global REPLIED_USERS, IGNORED_USERS
    try:
        sender = await event.get_sender()
        
        if sender and not getattr(sender, 'bot', False):
            user_id = event.sender_id
            
            # Block ලිස්ට් එකේ ඇත්නම් කිසිම Auto-reply එකක් නොයයි
            if user_id in IGNORED_USERS:
                return

            incoming_raw = event.raw_text.strip().lower()
            replied = False
            
            for word, reply in RESPONSES.items():
                target_word = word.strip().lower()
                if target_word and (target_word == incoming_raw or target_word in incoming_raw.split()):
                    await event.reply(reply)
                    replied = True
                    break
                    
            if not replied:
                if user_id not in REPLIED_USERS:
                    await event.reply("මං පොඩි වැඩක ඉන්නේ. 💻 මේක Auto Reply එකක්, ආපු ගමන් මැසේජ් එකක් දාන්නම් හොඳේ! ✨")
                    REPLIED_USERS.add(user_id)
    except Exception:
        pass

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

if __name__ == "__main__":
    t = threading.Thread(target=run_flask)
    t.daemon = True
    t.start()
    
    print("Userbot එක සාර්ථකව වැඩ කරමින් පවතී...")
    
    async def start_bot():
        await client.start()
        await load_bot_data()  # Saved Messages වලින් Block list එක load කිරීම
        try:
            await client.send_message('me', "🚀 **Userbot Started Successfully with Permanent Data Persistence!**")
        except Exception:
            pass
        await client.run_until_disconnected()

    client.loop.run_until_complete(start_bot())
