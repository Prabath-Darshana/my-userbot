import json
import os
from telethon import TelegramClient, events

api_id = 35039780
api_hash = '4ec122e3bde00836e5a02223c5a7714d'

client = TelegramClient('my_userbot_session', api_id, api_hash)

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

print("Userbot එක සාර්ථකව වැඩ කරමින් පවතී...")
client.start()
client.run_until_disconnected()
