import json
import os
import threading
from flask import Flask
from telethon import TelegramClient, events
from telethon.sessions import StringSession

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
    try:
        raw_text = event.raw_text.strip()
        lines = raw_text.split('\n')
        added_count = 0
        added_list = []

        # 1. !add Command එක (Multi-line support)
        for line in lines:
            line = line.strip()
            if line.startswith("!add "):
                try:
                    content = line[5:]
                    if "=" in content:
                        word, reply = content.split("=", 1)
                        word = word.strip().lower()
                        reply = reply.strip()
                        
                        RESPONSES[word] = reply
                        added_list.append(f"`{word}` ➔ {reply}")
                        added_count += 1
                except Exception:
                    pass

        if added_count > 0:
            save_responses(RESPONSES)
            if added_count == 1:
                await event.edit(f"✅ **එකතු කළා:**\n{added_list[0]}")
            else:
                await event.edit(f"✅ **Auto Replies {added_count}ක් සාර්ථකව එකතු කළා!**")
            return

        # 2. !del Command එක
        if raw_text.startswith("!del "):
            word = raw_text[5:].strip().lower()
            if word in RESPONSES:
                del RESPONSES[word]
                save_responses(RESPONSES)
                await event.edit(f"🗑️ `{word}` **අයින් කළා.**")
            else:
                await event.edit(f"❌ `{word}` සොයාගත නොහැකි විය.")

        # 3. !clear Command එක
        elif raw_text == "!clear":
            RESPONSES = {}
            save_responses(RESPONSES)
            await event.edit("🗑️ **ලැයිස්තුවේ තිබූ සියලුම Auto Replies මකා දමන ලදී!**")

        # 4. !list Command එක
        elif raw_text == "!list":
            if not RESPONSES:
                await event.edit("📝 **ලැයිස්තුව හිස්ය.**")
                return
            msg = f"📝 **දැනට ඇති Auto Replies ({len(RESPONSES)}):**\n\n"
            for w, r in RESPONSES.items():
                msg += f"• `{w}` ➔ {r}\n"
            await event.edit(msg)
    except Exception:
        pass

@client.on(events.NewMessage(incoming=True, func=lambda e: e.is_private))
async def reply_handler(event):
    try:
        sender = await event.get_sender()
        
        # Bot කෙනෙක් නෙමෙයි නම් පමණක් Reply කිරීම
        if sender and not getattr(sender, 'bot', False):
            text = event.raw_text.lower()
            replied = False
            
            # 1. Custom list එකේ තිබෙන වචන වලට Text reply එක යැවීම
            for word, reply in RESPONSES.items():
                if word in text:
                    await event.reply(reply)
                    replied = True
                    break
                    
            # 2. List එකේ නැති වෙනත් ඕනෑම මැසේජ් එකකට Default Message එක යැවීම
            if not replied:
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
    
    # Crash නොවීම සඳහා Infinite Loop එකක්
    while True:
        try:
            client.start()
            client.run_until_disconnected()
        except Exception as e:
            print(f"Error එකක් ආවා, නැවත Start වේ: {e}")
