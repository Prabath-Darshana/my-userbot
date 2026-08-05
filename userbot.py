import json
import os
import threading
from flask import Flask
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.types import UserStatusOnline

# 1. Render Port Binding සඳහා Flask App එක
app = Flask(__name__)

@app.route('/')
def home():
    return "Userbot is Live!"

# 2. Telegram Credentials
api_id = 35039780
api_hash = '4ec122e3bde00836e5a02223c5a7714d'

session_str = os.environ.get("STRING_SESSION", "")

client = TelegramClient(StringSession(session_str), api_id, api_hash)

DATA_FILE = 'responses.json'

def load_responses():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    else:
        return {}

def save_responses(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

RESPONSES = load_responses()

@client.on(events.NewMessage(outgoing=True))
async def command_handler(event):
    global RESPONSES
    text = event.raw_text.strip()
    
    if text.startswith("!add "):
        try:
            content = text[5:]
            word, reply = content.split("=", 1)
            word = word.strip().lower()
            reply = reply.strip()
            
            RESPONSES[word] = reply
            save_responses(RESPONSES)
            await event.edit(f"✅ **එකතු කළා:**\n`{word}` ➔ {reply}")
        except Exception:
            await event.edit("❌ **භාවිතය:** `!add word=reply` ලෙස යවන්න.")

    elif text.startswith("!del "):
        word = text[5:].strip().lower()
        if word in RESPONSES:
            del RESPONSES[word]
            save_responses(RESPONSES)
            await event.edit(f"🗑️ `{word}` **අයින් කළා.**")
        else:
            await event.edit(f"❌ `{word}` සොයාගත නොහැකි විය.")

    elif text == "!clear":
        RESPONSES = {}
        save_responses(RESPONSES)
        await event.edit("🗑️ **ලැයිස්තුවේ තිබූ සියලුම Auto Replies මකා දමන ලදී!**")

    elif text == "!list":
        if not RESPONSES:
            await event.edit("📝 **ලැයිස්තුව හිස්ය.**")
            return
        msg = "📝 **දැනට ඇති Auto Replies:**\n\n"
        for w, r in RESPONSES.items():
            msg += f"• `{w}` ➔ {r}\n"
        await event.edit(msg)

@client.on(events.NewMessage(incoming=True, func=lambda e: e.is_private))
async def reply_handler(event):
    sender = await event.get_sender()
    
    if not sender.bot:
        text = event.raw_text.lower()
        replied = False
        
        # 1. List එකේ ඇති වචනයක්දැයි පරීක්ෂා කිරීම
        for word, reply in RESPONSES.items():
            if word in text:
                await event.reply(reply)
                replied = True
                break
                
        # 2. List එකේ නැත්නම් සහ Offline නම් පමණක් Default reply එක යැවීම
        if not replied:
            try:
                me = await client.get_me()
                is_online = isinstance(getattr(me, 'status', None), UserStatusOnline)
                
                if not is_online:
                    await event.reply("අඩෝ මම පොඩ්ඩක් Offline ඉන්නේ බං. 💻 ආපු ගමන් මැසේජ් එකක් දාන්නම්!")
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
    client.start()
    client.run_until_disconnected()
