import json
import os
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

# Render Environment Variable එකෙන් Session එක ගනී
session_str = os.environ.get("STRING_SESSION", "1BVtsOJ8Bu3cBYUVe60MSz_ToaJx0fgWtHKvQVOghWEoKsQbrduiE-pmAGAQeHQHZKqdwb6i3n7F2rCaySPAome7IQaK4G95DFdZ108ffCVBJ8aej5awj1krbXB5HmvQJ5GvlUuxn566YdKwJUIo2OKmzOgEF-cGB9UBKlOMvioa-HnzSLE0P-hEF5KVXf2zW9l4JUsEGSc39wCaQGusnhD2mc1dmdJH9y9GblbESFrLFTY7RV55-NMpn26Hvf65zpFbGDz14vy4jYjP-K2DEAQL21rIuPFtSoQfWMMwCBpeHbKgbQuHMiJ5hUKtac5qpkLxW2I0v0Mhvdmq99koRh5nW-U9mDmQ=")

client = TelegramClient(StringSession(session_str), api_id, api_hash)

DATA_FILE = 'responses.json'

def load_responses():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    else:
        default_data = {
            "hi": "හලෝ මචං! කොහොමද ඉතින්?",
            "hello": "හලෝ මචං! කොහොමද ඉතින්?",
            "මචං": "කියපන් මචෝ, මොකද වෙන්නේ?",
            "moko": "ලැප් එකේ වැඩක් බං. කියපන්?",
            "ela": "එලම කිරි මචං! 👍",
            "thanks": "Welcome මචං! 🤜🤛",
            "bye": "එල බං, Bye! පරිස්සමෙන්."
        }
        save_responses(default_data)
        return default_data

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
        
        for word, reply in RESPONSES.items():
            if word in text:
                await event.reply(reply)
                replied = True
                break
                
        if not replied:
            await event.reply("අඩෝ මම පොඩ්ඩක් Offline ඉන්නේ බං. 💻 ආපු ගමන් මැසේජ් එකක් දාන්නම්!")

# Telegram Bot එක Background එකේ Connect කිරීම
client.loop.create_task(client.start())

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    # Flask main process එක ලෙස Run වන නිසා Render එකට Port එක ඉක්මනින් Detect වේ
    app.run(host="0.0.0.0", port=port)
