import json
import os
import re
import time
import threading
from datetime import datetime
import pytz
import requests
import yt_dlp
from flask import Flask
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.functions.users import GetFullUserRequest
from google import genai

app = Flask(__name__)

@app.route('/')
def home():
    return "Lankan Power Userbot is Live!"

# Telegram API Credentials
api_id = 35039780
api_hash = '4ec122e3bde00836e5a02223c5a7714d'

# Gemini AI (New SDK)
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
ai_client = None

if GEMINI_API_KEY:
    try:
        ai_client = genai.Client(api_key=GEMINI_API_KEY)
    except Exception as e:
        print(f"AI Setup Error: {e}")

STORAGE_CHANNEL = -1004489211765
session_str = os.environ.get("STRING_SESSION", "")
client = TelegramClient(StringSession(session_str), api_id, api_hash, sequential_updates=True)

# Variables
RESPONSES = {}
MEDIA_RESPONSES = {}
IGNORED_USERS = set()
REPLIED_USERS = set()
KNOWN_CONTACTS = set()
TODO_LIST = []
USER_LAST_MSG_TIME = {}

AFK_MODE = False
AFK_REASON = ""
WORKING_HOURS_ONLY = False
START_HOUR = 1
END_HOUR = 7
WELCOME_MSG_ENABLED = True
AI_REPLY_ENABLED = True
PM_GUARD_ENABLED = True

async def load_bot_data():
    global RESPONSES, MEDIA_RESPONSES, IGNORED_USERS, WORKING_HOURS_ONLY, START_HOUR, END_HOUR, WELCOME_MSG_ENABLED, KNOWN_CONTACTS, TODO_LIST, AI_REPLY_ENABLED, PM_GUARD_ENABLED
    try:
        async for msg in client.iter_messages(STORAGE_CHANNEL, search="[USERBOT_DATA_SAVE]"):
            if msg.text and "[USERBOT_DATA_SAVE]" in msg.text:
                json_str = msg.text.split("[USERBOT_DATA_SAVE]")[1].strip()
                data = json.loads(json_str)
                RESPONSES = data.get("responses", {})
                MEDIA_RESPONSES = data.get("media_responses", {})
                IGNORED_USERS = set(data.get("ignored", []))
                KNOWN_CONTACTS = set(data.get("known_contacts", []))
                WORKING_HOURS_ONLY = data.get("working_hours", False)
                START_HOUR = data.get("start_hour", 1)
                END_HOUR = data.get("end_hour", 7)
                WELCOME_MSG_ENABLED = data.get("welcome_msg", True)
                AI_REPLY_ENABLED = data.get("ai_reply", True)
                PM_GUARD_ENABLED = data.get("pm_guard", True)
                TODO_LIST = data.get("todo_list", [])
                break
    except Exception as e:
        print(f"Data Load Error: {e}")

async def save_bot_data():
    global RESPONSES, MEDIA_RESPONSES, IGNORED_USERS, WORKING_HOURS_ONLY, START_HOUR, END_HOUR, WELCOME_MSG_ENABLED, KNOWN_CONTACTS, TODO_LIST, AI_REPLY_ENABLED, PM_GUARD_ENABLED
    try:
        data = {
            "responses": RESPONSES,
            "media_responses": MEDIA_RESPONSES,
            "ignored": list(IGNORED_USERS),
            "known_contacts": list(KNOWN_CONTACTS),
            "working_hours": WORKING_HOURS_ONLY,
            "start_hour": START_HOUR,
            "end_hour": END_HOUR,
            "welcome_msg": WELCOME_MSG_ENABLED,
            "ai_reply": AI_REPLY_ENABLED,
            "pm_guard": PM_GUARD_ENABLED,
            "todo_list": TODO_LIST
        }
        text_to_save = f"[USERBOT_DATA_SAVE]\n{json.dumps(data, ensure_ascii=False)}"
        async for msg in client.iter_messages(STORAGE_CHANNEL, search="[USERBOT_DATA_SAVE]"):
            await msg.delete()
        await client.send_message(STORAGE_CHANNEL, text_to_save)
    except Exception as e:
        print(f"Data Save Error: {e}")

# OUTGOING COMMANDS HANDLER
@client.on(events.NewMessage(outgoing=True))
async def command_handler(event):
    global RESPONSES, MEDIA_RESPONSES, IGNORED_USERS, REPLIED_USERS, AFK_MODE, AFK_REASON, WORKING_HOURS_ONLY, START_HOUR, END_HOUR, WELCOME_MSG_ENABLED, KNOWN_CONTACTS, TODO_LIST, AI_REPLY_ENABLED, PM_GUARD_ENABLED
    try:
        raw_text = event.raw_text.strip() if event.raw_text else ""
        if not raw_text:
            return

        if AFK_MODE and not raw_text.startswith("!afk"):
            AFK_MODE = False
            AFK_REASON = ""
            await client.send_message(STORAGE_CHANNEL, "🟢 **AFK Mode Turn Off විය.**")

        # STATUS / DASHBOARD
        if raw_text == "!status":
            status_msg = (
                "🇱🇰 **Lankan Ultimate Userbot Dashboard**\n\n"
                "⚙️ **System Settings**\n"
                f" ├ AFK Mode ➔ {'🟢 ON' if AFK_MODE else '🔴 OFF'}\n"
                f" ├ PM Spam Guard ➔ {'🟢 ON' if PM_GUARD_ENABLED else '🔴 OFF'}\n"
                f" ├ Working Hours ➔ {'🟢 ON' if WORKING_HOURS_ONLY else '🔴 OFF'} ({START_HOUR}:00 - {END_HOUR}:00)\n"
                f" ├ Smart AI Auto-Reply ➔ {'🟢 ON' if AI_REPLY_ENABLED else '🔴 OFF'}\n"
                f" └ Custom Replies ➔ `{len(RESPONSES)}` Text | `{len(MEDIA_RESPONSES)}` Media\n\n"
                "🛠️ **Power User Commands**\n"
                " ➦ `!song <name>` - Download Songs (MP3)\n"
                " ➦ `!yt <link>` - Download Video\n"
                " ➦ `!voice` (Reply) - Voice Note to Text\n"
                " ➦ `!sum <link>` - Web/Article Summary\n"
                " ➦ `!weather <city>` - Colombo/Kandy Weather\n"
                " ➦ `!convert <amount> <from> to <to>` - Currency Rate\n"
                " ➦ `!guard on/off` - Smart Spam Protection\n"
                " ➦ `!ai on/off` - Gemini AI Auto Reply\n"
                " ➦ `!block` / `!unblock` / `!gcast <msg>`\n\n"
                "> 🇱🇰 **Sri Lankan Power Userbot - Ready to Roll!**"
            )
            await event.edit(status_msg)
            return

        # 1. YOUTUBE / SONG DOWNLOADER
        if raw_text.startswith("!song ") or raw_text.startswith("!yt "):
            query = raw_text.split(" ", 1)[1]
            await event.edit(f"📥 **Downloading `{query}`... Poddak ඉන්න!**")
            ydl_opts = {
                'format': 'bestaudio/best' if raw_text.startswith("!song") else 'best',
                'outtmpl': 'downloaded_media.%(ext)s',
                'quiet': True,
                'no_warnings': True
            }
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(f"ytsearch:{query}" if not query.startswith("http") else query, download=True)
                    filename = ydl.prepare_filename(info if 'entries' not in info else info['entries'][0])
                await event.edit("⬆️ **Uploading to Telegram...**")
                await client.send_file(event.chat_id, filename)
                await event.delete()
                if os.path.exists(filename):
                    os.remove(filename)
            except Exception as ex:
                await event.edit(f"❌ **Download Error:** `{ex}`")
            return

        # 2. VOICE-TO-TEXT (TRANSCRIBER)
        if raw_text == "!voice" and event.is_reply:
            reply_msg = await event.get_reply_message()
            if reply_msg and reply_msg.voice and ai_client:
                await event.edit("🎙️ **Voice note එක අහන ගමන් (Converting to Text)...**")
                file_path = await reply_msg.download_media()
                try:
                    # Send audio to Gemini
                    audio_file = ai_client.files.upload(file=file_path)
                    response = ai_client.models.generate_content(
                        model='gemini-2.5-flash',
                        contents=['Translate and transcribe this audio voice note into clear Sinhala and English text:', audio_file]
                    )
                    await event.edit(f"📝 **Voice Note Text:**\n\n{response.text}")
                except Exception as ve:
                    await event.edit(f"❌ Voice Process Error: `{ve}`")
                if os.path.exists(file_path):
                    os.remove(file_path)
            return

        # 3. LINK SUMMARIZER
        if raw_text.startswith("!sum "):
            link = raw_text[5:].strip()
            if ai_client:
                await event.edit("🌐 **Reading Web Link & Summarizing...**")
                try:
                    res = requests.get(link, timeout=10)
                    content = res.text[:4000] # Trim text
                    prompt = f"Summarize this web page content in simple Singlish/Sinhala with key bullet points: {content}"
                    ai_res = ai_client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
                    await event.edit(f"📌 **Summary:**\n\n{ai_res.text}")
                except Exception as se:
                    await event.edit(f"❌ Summary Error: `{se}`")
            return

        # 4. WEATHER INFO
        if raw_text.startswith("!weather "):
            city = raw_text[9:].strip()
            try:
                res = requests.get(f"https://wttr.in/{city}?format=%C+%t+%w+%h").text
                await event.edit(f"☀️ **Weather in {city.capitalize()}:**\n`{res}`")
            except Exception:
                await event.edit("❌ Weather data ලබාගැනීමට නොහැකි විය.")
            return

        # 5. CURRENCY CONVERTER
        if raw_text.startswith("!convert "):
            try:
                parts = raw_text[9:].strip().split()
                amount, from_curr, to_curr = float(parts[0]), parts[1].upper(), parts[3].upper()
                res = requests.get(f"https://api.exchangerate-api.com/v4/latest/{from_curr}").json()
                rate = res['rates'][to_curr]
                total = amount * rate
                await event.edit(f"🎛️ `{amount} {from_curr}` = **`{total:,.2f} {to_curr}`**")
            except Exception:
                await event.edit("❌ Format: `!convert 100 usd to lkr`")
            return

        # TOGGLES & BASIC CMDS
        if raw_text.startswith("!guard "):
            arg = raw_text[7:].strip().lower()
            PM_GUARD_ENABLED = (arg == "on")
            await save_bot_data()
            await event.edit(f"🛡️ **PM Spam Guard {'ON' if PM_GUARD_ENABLED else 'OFF'} කරන ලදී.**")
            return

        if raw_text.startswith("!ai "):
            arg = raw_text[4:].strip().lower()
            AI_REPLY_ENABLED = (arg == "on")
            await save_bot_data()
            await event.edit(f"🤖 **Gemini AI Reply {'ON' if AI_REPLY_ENABLED else 'OFF'} කරන ලදී.**")
            return

    except Exception:
        pass

# INCOMING MESSAGES (LANKAN PERSONALITY AI + SPAM GUARD)
@client.on(events.NewMessage(incoming=True, func=lambda e: e.is_private))
async def incoming_handler(event):
    global REPLIED_USERS, IGNORED_USERS, AFK_MODE, AFK_REASON, KNOWN_CONTACTS, USER_LAST_MSG_TIME
    try:
        user_id = event.sender_id
        if not user_id or user_id in IGNORED_USERS:
            return

        # Anti-Spam Cooldown
        current_time = time.time()
        if user_id in USER_LAST_MSG_TIME and (current_time - USER_LAST_MSG_TIME[user_id] < 8):
            return
        USER_LAST_MSG_TIME[user_id] = current_time

        # PM Guard System for Unknown Users
        if PM_GUARD_ENABLED and user_id not in KNOWN_CONTACTS:
            try:
                full_user = await client(GetFullUserRequest(user_id))
                user_obj = full_user.users[0]
                if not user_obj.contact and not user_obj.bot:
                    await event.reply("🛡️ **PM Protection:** Halo! Mawa aduranne nattam wistara kiyala inna. Owner online apu gaman reply karai! 👍")
                    KNOWN_CONTACTS.add(user_id)
                    await save_bot_data()
                    return
            except Exception:
                pass

        if AFK_MODE:
            await event.reply(f"🤖 **AFK Mode Active:** {AFK_REASON}")
            return

        incoming_raw = event.raw_text.strip() if event.raw_text else ""
        if not incoming_raw:
            return

        # Gemini AI Lankan Personality Reply
        if AI_REPLY_ENABLED and ai_client and user_id not in REPLIED_USERS:
            try:
                prompt = (
                    "You are an intelligent Sri Lankan personal Telegram assistant. "
                    "Reply to this incoming message naturally in friendly Singlish (Sinhala written in English letters) "
                    "or Sinhala in 1-2 short sentences like a real Sri Lankan friend (use words like Machan, Aney, Hari, Bro where suitable): "
                    f"'{incoming_raw}'"
                )
                response = ai_client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
                if response.text:
                    await event.reply(f"{response.text.strip()}\n\n_(🤖 Auto Assistant)_")
                    REPLIED_USERS.add(user_id)
            except Exception as ai_err:
                print(f"AI Error: {ai_err}")

    except Exception:
        pass

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
        await client.run_until_disconnected()

    client.loop.run_until_complete(start_bot())
