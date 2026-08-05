import json
import os
import re
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

DATA_FILE = 'responses.json'
IGNORED_FILE = 'ignored_users.json'

replied_users = set()

def load_data(file_path, default):
    if os.path.exists(file_path):
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return default

def save_data(file_path, data):
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

RESPONSES = load_data(DATA_FILE, {})
IGNORED_USERS = set(load_data(IGNORED_FILE, []))

def clean_text(text):
    if not text:
        return ""
    text = text.lower()
    text = re.sub(r'[^\w\s]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

@client.on(events.NewMessage(outgoing=True))
async def command_handler(event):
    global RESPONSES, IGNORED_USERS, replied_users
    try:
        raw_text = event.raw_text.strip()
        lines = raw_text.split('\n')
        added_count = 0
        added_list = []

        # 1. !block (මැසේජ් එකකට reply කරලා යැවිය යුතුයි)
        if raw_text == "!block" and event.is_reply:
            reply_msg = await event.get_reply_message()
            user_id = reply_msg.sender_id
            IGNORED_USERS.add(user_id)
            save_data(IGNORED_FILE, list(IGNORED_USERS))
            await event.edit("🚫 **මෙම කෙනාට Auto-Reply නතර කරන ලදී!**")
            return

        # 2. !unblock (මැසේජ් එකකට reply කරලා යැවිය යුතුයි)
        if raw_text == "!unblock" and event.is_reply:
            reply_msg = await event.get_reply_message()
            user_id = reply_msg.sender_id
            if user_id in IGNORED_USERS:
                IGNORED_USERS.remove(user_id)
                save_data(IGNORED_FILE, list(IGNORED_USERS))
                await event.edit("✅ **මෙම කෙනාට නැවත Auto-Reply සක්‍රිය කළා!**")
            else:
                await event.edit("❌ **මෙම කෙනා Block ලැයිස්තුවේ නැත.**")
            return

        # 3. !blocklist
        if raw_text == "!blocklist":
            await event.edit(f"🚫 **Auto-Reply Off කර ඇති ගණන:** `{len(IGNORED_USERS)}`")
            return

        # 4. !add Command එක
        for line in lines:
            line = line.strip()
            if line.startswith("!add "):
                try:
                    content = line[5:]
                    if "=" in content:
                        word, reply = content.split("=", 1)
                        word = clean_text(word)
                        reply = reply.strip()
                        
                        if word:
                            RESPONSES[word] = reply
                            added_list.append(f"`{word}` ➔ {reply}")
                            added_count += 1
                except Exception:
                    pass

        if added_count > 0:
            save_data(DATA_FILE, RESPONSES)
            if added_count == 1:
                await event.edit(f"✅ **එකතු කළා:**\n{added_list[0]}")
            else:
                await event.edit(f"✅ **Auto Replies {added_count}ක් එකතු කළා!**")
            return

        # 5. !del Command එක
        if raw_text.startswith("!del "):
            word = clean_text(raw_text[5:])
            if word in RESPONSES:
                del RESPONSES[word]
                save_data(DATA_FILE, RESPONSES)
                await event.edit(f"🗑️ `{word}` **අයින් කළා.**")
            else:
                await event.edit(f"❌ `{word}` සොයාගත නොහැකි විය.")

        # 6. !clear
        elif raw_text == "!clear":
            RESPONSES = {}
            save_data(DATA_FILE, RESPONSES)
            await event.edit("🗑️ **සියලුම Auto Replies මකා දමන ලදී!**")

        # 7. !list
        elif raw_text == "!list":
            if not RESPONSES:
                await event.edit("📝 **ලැයිස්තුව හිස්ය.**")
                return
            msg = f"📝 **දැනට ඇති Auto Replies ({len(RESPONSES)}):**\n\n"
            for w, r in RESPONSES.items():
                msg += f"• `{w}` ➔ {r}\n"
            await event.edit(msg)

        # 8. !reset
        elif raw_text == "!reset":
            replied_users.clear()
            await event.edit("🔄 **Auto-Reply History එක Reset කළා!**")
    except Exception:
        pass

@client.on(events.NewMessage(incoming=True, func=lambda e: e.is_private))
async def reply_handler(event):
    global replied_users, IGNORED_USERS
    try:
        sender = await event.get_sender()
        
        if sender and not getattr(sender, 'bot', False):
            user_id = event.sender_id
            
            # 🚫 Block කල කෙනෙක් නම් Bot කිසිවක් නොකරයි
            if user_id in IGNORED_USERS:
                return

            incoming_raw = event.raw_text
            cleaned_incoming = clean_text(incoming_raw)
            replied = False
            
            # 1. Custom list matching
            for word, reply in RESPONSES.items():
                clean_target_word = clean_text(word)
                if clean_target_word and (clean_target_word == cleaned_incoming or clean_target_word in cleaned_incoming.split()):
                    await event.reply(reply)
                    replied = True
                    break
                    
            # 2. Default Message (Friendly text)
            if not replied:
                if user_id not in replied_users:
                    await event.reply("මං පොඩි වැඩක ඉන්නේ. 💻 මේක Auto Reply එකක්, ආපු ගමන් මැසේජ් එකක් දාන්නම් හොඳේ! ✨")
                    replied_users.add(user_id)
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
    
    while True:
        try:
            client.start()
            client.run_until_disconnected()
        except Exception as e:
            print(f"Update Loop Warning: {e}")
