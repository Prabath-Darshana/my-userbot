import json
import os
import re
import time
import asyncio
import threading
from datetime import datetime
import pytz
from flask import Flask
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.functions.users import GetFullUserRequest
from telethon.tl.types import UserStatusOnline
from google import genai
import yt_dlp

app = Flask(__name__)

@app.route('/')
def home():
    return "Userbot Utility Active!"

# ---------------- CONFIGURATION ----------------
API_ID = 35039780
API_HASH = '4ec122e3bde00836e5a02223c5a7714d'
STORAGE_CHANNEL = -1004489211765
AL_EXAM_DATE = datetime(2028, 8, 10)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
ai_client = None

if GEMINI_API_KEY:
    try:
        ai_client = genai.Client(api_key=GEMINI_API_KEY)
    except Exception as e:
        print(f"AI Client Setup Error: {e}")

session_str = os.environ.get("STRING_SESSION", "")
client = TelegramClient(StringSession(session_str), API_ID, API_HASH, sequential_updates=True)

# System Variables
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

# ---------------- DATA PERSISTENCE ----------------
async def load_bot_data():
    global RESPONSES, MEDIA_RESPONSES, IGNORED_USERS, WORKING_HOURS_ONLY, START_HOUR, END_HOUR, WELCOME_MSG_ENABLED, KNOWN_CONTACTS, TODO_LIST, AI_REPLY_ENABLED
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
                TODO_LIST = data.get("todo_list", [])
                break
    except Exception as e:
        print(f"Data Load Error: {e}")

async def save_bot_data():
    global RESPONSES, MEDIA_RESPONSES, IGNORED_USERS, WORKING_HOURS_ONLY, START_HOUR, END_HOUR, WELCOME_MSG_ENABLED, KNOWN_CONTACTS, TODO_LIST, AI_REPLY_ENABLED
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
            "todo_list": TODO_LIST
        }
        text_to_save = f"[USERBOT_DATA_SAVE]\n{json.dumps(data, ensure_ascii=False)}"
        async for msg in client.iter_messages(STORAGE_CHANNEL, search="[USERBOT_DATA_SAVE]"):
            await msg.delete()
        await client.send_message(STORAGE_CHANNEL, text_to_save)
    except Exception as e:
        print(f"Data Save Error: {e}")

# Helper: Check if account owner is online
async def is_owner_online():
    try:
        me = await client.get_me()
        user_full = await client(GetFullUserRequest(me.id))
        return isinstance(user_full.users[0].status, UserStatusOnline)
    except Exception:
        return False

# ---------------- OWNER COMMANDS (OUTGOING) ----------------
@client.on(events.NewMessage(outgoing=True))
async def command_handler(event):
    global RESPONSES, MEDIA_RESPONSES, IGNORED_USERS, REPLIED_USERS, AFK_MODE, AFK_REASON, WORKING_HOURS_ONLY, WELCOME_MSG_ENABLED, KNOWN_CONTACTS, TODO_LIST, AI_REPLY_ENABLED
    try:
        raw_text = event.raw_text.strip() if event.raw_text else ""
        if not raw_text:
            return

        if AFK_MODE and not raw_text.startswith("!afk"):
            AFK_MODE = False
            AFK_REASON = ""
            await client.send_message(STORAGE_CHANNEL, "🟢 **AFK Mode එක Off වුණා.**")

        # 1. STATUS / DASHBOARD
        if raw_text == "!status":
            tz = pytz.timezone('Asia/Colombo')
            now = datetime.now(tz).replace(tzinfo=None)
            days_left = (AL_EXAM_DATE - now).days

            todo_str = ""
            if TODO_LIST:
                for idx, task in enumerate(TODO_LIST, 1):
                    prefix = "└" if idx == len(TODO_LIST) else "├"
                    todo_str += f" {prefix} {idx}. {task}\n"
            else:
                todo_str = " └ No active targets set\n"

            status_msg = (
                "👋 **Hello, Student!**\n\n"
                f"🎯 **A/L Exam Countdown (2028-08-10)**\n"
                f" └ `{days_left} Days Remaining!`\n\n"
                "⚙️ **System Settings**\n"
                f" ├ AFK Mode ➔ {'🟢 ON' if AFK_MODE else '🔴 OFF'}\n"
                f" ├ Working Hours ➔ {'🟢 ON' if WORKING_HOURS_ONLY else '🔴 OFF'}\n"
                f" ├ Welcome Message ➔ {'🟢 ON' if WELCOME_MSG_ENABLED else '🔴 OFF'}\n"
                f" ├ Custom Text Replies ➔ `{len(RESPONSES)} Units`\n"
                f" ├ Custom Media Replies ➔ `{len(MEDIA_RESPONSES)} Units`\n"
                f" └ Blocked Users ➔ `{len(IGNORED_USERS)} Users`\n\n"
                f"📌 **Daily Study Targets**\n{todo_str}\n"
                "🤖 **Bot Commands** 👇\n\n"
                " ➦ `!status` - Dashboard & Countdown\n"
                " ➦ `!todo <target>` - Target එකක් එකතු කිරීමට\n"
                " ➦ `!done <number>` - Target එක Complete කිරීමට\n"
                " ➦ `!cleartodo` - Targets Clear කිරීමට\n"
                " ➦ `!afk <reason>` / `!afk off` - AFK On/Off\n"
                " ➦ `!hours on` / `!hours off` - Working Hours\n"
                " ➦ `!welcome on` / `!welcome off` - Welcome Msg\n"
                " ➦ `!add word=reply` - Auto Reply එකතු කිරීමට\n"
                " ➦ `!addmedia word` - Media Auto Reply\n"
                " ➦ `!delmedia word` - Media Reply අයින් කිරීමට\n"
                " ➦ `!list` / `!listmedia` - Auto Replies ලැයිස්තුව\n"
                " ➦ `!block` / `!unblock` - Block/Unblock Chat\n"
                " ➦ `!gcast <msg>` - Message Broadcast\n"
                " ➦ `!reset` - Clear History & Contacts\n\n"
                "💡 **A/L Combined Maths Userbot System**\n"
                "🚀 Status: Active & Operational"
            )
            await event.edit(status_msg)
            return

        # 2. TODO TARGET COMMANDS
        if raw_text.startswith("!todo "):
            task = raw_text[6:].strip()
            if task:
                TODO_LIST.append(task)
                await save_bot_data()
                await event.edit(f"✅ **Target එකතු කළා:** `{task}`")
            return

        if raw_text.startswith("!done "):
            try:
                idx = int(raw_text[6:].strip()) - 1
                if 0 <= idx < len(TODO_LIST):
                    removed = TODO_LIST.pop(idx)
                    await save_bot_data()
                    await event.edit(f"🎉 **Target Completed:** `{removed}`")
                else:
                    await event.edit("❌ වැරදි අංකයකි.")
            except Exception:
                await event.edit("❌ Command එක වැරදියි. (e.g. `!done 1`)")
            return

        if raw_text == "!cleartodo":
            TODO_LIST.clear()
            await save_bot_data()
            await event.edit("🧹 **සියලුම Study Targets Clear කළා!**")
            return

        # 3. AFK COMMAND
        if raw_text.startswith("!afk"):
            arg = raw_text[4:].strip()
            if arg.lower() == "off":
                AFK_MODE = False
                await event.edit("🔴 **AFK Mode Off.**")
            else:
                AFK_REASON = arg or "වැඩක ඉන්නේ."
                AFK_MODE = True
                await event.edit(f"🟢 **AFK On!** Reason: `{AFK_REASON}`")
            return

        # 4. SYSTEM TOGGLES
        if raw_text.startswith("!hours "):
            val = raw_text[7:].strip().lower()
            WORKING_HOURS_ONLY = (val == "on")
            await save_bot_data()
            await event.edit(f"⚙️ **Working Hours:** `{'ON' if WORKING_HOURS_ONLY else 'OFF'}`")
            return

        if raw_text.startswith("!welcome "):
            val = raw_text[9:].strip().lower()
            WELCOME_MSG_ENABLED = (val == "on")
            await save_bot_data()
            await event.edit(f"⚙️ **Welcome Message:** `{'ON' if WELCOME_MSG_ENABLED else 'OFF'}`")
            return

        # 5. CUSTOM REPLIES
        if raw_text.startswith("!add ") and "=" in raw_text:
            parts = raw_text[5:].split("=", 1)
            key, val = parts[0].strip().lower(), parts[1].strip()
            RESPONSES[key] = val
            await save_bot_data()
            await event.edit(f"✅ Auto Reply එකතු කළා: `{key}` ➔ `{val}`")
            return

        if raw_text.startswith("!del "):
            key = raw_text[5:].strip().lower()
            if key in RESPONSES:
                del RESPONSES[key]
                await save_bot_data()
                await event.edit(f"🗑️ Auto reply අයින් කළා: `{key}`")
            return

        if raw_text == "!list":
            if not RESPONSES:
                await event.edit("📜 Text Auto Replies කිසිවක් නැත.")
                return
            msg = "📝 **Custom Text Replies:**\n\n"
            for k, v in RESPONSES.items():
                msg += f"• `{k}` ➔ {v}\n"
            await event.edit(msg)
            return

        # 6. MEDIA REPLIES
        if raw_text.startswith("!addmedia "):
            key = raw_text[10:].strip().lower()
            reply_msg = await event.get_reply_message()
            if reply_msg and reply_msg.media:
                MEDIA_RESPONSES[key] = reply_msg.id
                await save_bot_data()
                await event.edit(f"🖼️ Media reply එකතු කළා for: `{key}`")
            else:
                await event.edit("❌ Media Message එකකට Reply කර මේ Command එක දමන්න.")
            return

        if raw_text.startswith("!delmedia "):
            key = raw_text[10:].strip().lower()
            if key in MEDIA_RESPONSES:
                del MEDIA_RESPONSES[key]
                await save_bot_data()
                await event.edit(f"🗑️ Media reply අයින් කළා: `{key}`")
            return

        if raw_text == "!listmedia":
            if not MEDIA_RESPONSES:
                await event.edit("🖼️ Media Auto Replies කිසිවක් නැත.")
                return
            msg = "🖼️ **Custom Media Replies:**\n\n"
            for k in MEDIA_RESPONSES.keys():
                msg += f"• `{k}`\n"
            await event.edit(msg)
            return

        # 7. BLOCK & UNBLOCK
        if raw_text in ["!block", "!unblock"]:
            chat = await event.get_chat()
            if event.is_private:
                if raw_text == "!block":
                    IGNORED_USERS.add(chat.id)
                    await save_bot_data()
                    await event.edit("🚫 **User Blocked.**")
                else:
                    IGNORED_USERS.discard(chat.id)
                    await save_bot_data()
                    await event.edit("✅ **User Unblocked.**")
            return

        # 8. BROADCAST (!gcast)
        if raw_text.startswith("!gcast "):
            bc_msg = raw_text[7:].strip()
            if bc_msg:
                await event.edit("📢 **Broadcasting Message...**")
                sent_count = 0
                for user in list(KNOWN_CONTACTS):
                    try:
                        await client.send_message(user, bc_msg)
                        sent_count += 1
                        time.sleep(0.5)
                    except Exception:
                        pass
                await event.edit(f"✅ Broadcast Complete! Sent to `{sent_count}` users.")
            return

        # 9. RESET HISTORY
        if raw_text == "!reset":
            REPLIED_USERS.clear()
            KNOWN_CONTACTS.clear()
            await save_bot_data()
            await event.edit("🧹 **History & Known Contacts Cleared!**")
            return

    except Exception as e:
        print(f"Owner Handler Error: {e}")

# ---------------- PUBLIC & INCOMING HANDLER ----------------
@client.on(events.NewMessage(incoming=True, func=lambda e: e.is_private))
async def reply_handler(event):
    global REPLIED_USERS, IGNORED_USERS, AFK_MODE, AFK_REASON, WORKING_HOURS_ONLY, USER_LAST_MSG_TIME
    try:
        user_id = event.sender_id
        if not user_id or user_id in IGNORED_USERS:
            return

        incoming_raw = event.raw_text.strip() if event.raw_text else ""

        # ALWAYS SEND WELCOME MESSAGE FOR NEW CONTACTS (Online/Offline)
        if WELCOME_MSG_ENABLED and user_id not in KNOWN_CONTACTS:
            try:
                full_user = await client(GetFullUserRequest(user_id))
                user_obj = full_user.users[0]
                if not user_obj.contact and not user_obj.bot:
                    welcome_text = (
                        "💌 **Hey! Thanks for your message.**\n"
                        "මම දැනට පොඩි වැඩක ඉන්නේ, ඉක්මනින්ම reply කරන්නම්! 😊\n\n"
                        "💡 **මෙතෙක් මගෙන් ලබාගත හැකි පහසුකම්:**\n"
                        " ➦ `!ask <ප්‍රශ්නය>` - A/L පාඩම් වල ඕනෑම ප්‍රශ්නයක් නිරාකරණය කරගන්න\n"
                        " ➦ `!ytmp3 <Link>` - YouTube සින්දු MP3 විදිහට Download කරගන්න\n"
                        " ➦ `!help` - සියලුම Commands බලාගන්න"
                    )
                    await event.reply(welcome_text)
                    KNOWN_CONTACTS.add(user_id)
                    await save_bot_data()
            except Exception as ex:
                print(f"Welcome Fetch Error: {ex}")

        if not incoming_raw:
            return

        # PUBLIC COMMAND 1: HELP
        if incoming_raw.lower() in ["!help", "/help", "help"]:
            help_text = (
                "🤖 **Assistant Public Commands:**\n\n"
                " ➦ `!ask <Question>` - Maths, Physics, Chem ඇතුළු ඕනෑම Study ප්‍රශ්නයක් අහන්න\n"
                " ➦ `!ytmp3 <YouTube Link>` - Audio Download කරගන්න\n"
                " ➦ `!exam` - A/L Exam Countdown එක බලන්න"
            )
            await event.reply(help_text)
            return

        # PUBLIC COMMAND 2: A/L COUNTDOWN
        if incoming_raw.lower() == "!exam":
            tz = pytz.timezone('Asia/Colombo')
            now = datetime.now(tz).replace(tzinfo=None)
            days_left = (AL_EXAM_DATE - now).days
            await event.reply(f"🎯 **2028 A/L Exam එකට තව දින `{days_left}` ක් තියෙනවා!**\n\n_Good Luck with your Studies!_ 📚")
            return

        # PUBLIC COMMAND 3: GENERAL STUDY HELPER (!ask)
        if incoming_raw.lower().startswith("!ask "):
            query = incoming_raw[5:].strip()
            if ai_client and query:
                status_msg = await event.reply("🧠 **ප්‍රශ්නය විශ්ලේෂණය කරමින් පවතී...**")
                try:
                    prompt = (
                        f"You are an expert A/L tutor (Maths, Physics, Chemistry, etc.). "
                        f"Solve or explain this question clearly step-by-step in Sinhala/Singlish: '{query}'"
                    )
                    response = ai_client.models.generate_content(
                        model='gemini-2.5-flash',
                        contents=prompt,
                    )
                    await status_msg.edit(f"📚 **Study Solution:**\n\n{response.text}")
                except Exception:
                    await status_msg.edit("❌ උත්තරය සොයාගැනීමට නොහැකි විය. කරුණාකර ප්‍රශ්නය පැහැදිලිව යොමු කරන්න.")
            return

        # PUBLIC COMMAND 4: YOUTUBE MP3 DOWNLOADER
        if incoming_raw.lower().startswith("!ytmp3 "):
            url = incoming_raw[7:].strip()
            if "youtube.com" in url or "youtu.be" in url:
                status_msg = await event.reply("📥 **YouTube MP3 Download වෙමින් පවතී...**")
                try:
                    ydl_opts = {
                        'format': 'bestaudio/best',
                        'outtmpl': 'downloads/%(id)s.%(ext)s',
                        'max_filesize': 50 * 1024 * 1024,
                    }
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(url, download=True)
                        filename = ydl.prepare_filename(info)

                    await status_msg.edit("⬆️ **Audio එක Telegram එකට Upload වෙමින් පවතී...**")
                    await client.send_file(event.chat_id, filename, caption=f"🎵 **{info.get('title')}**\n\nDownloaded via Assistant Bot")
                    await status_msg.delete()
                    if os.path.exists(filename):
                        os.remove(filename)
                except Exception:
                    await status_msg.edit("❌ **Download Error:** File එක විශාල වැඩියි හෝ Link එක වැරදියි.")
            return

        # CHECK CUSTOM TEXT REPLIES
        if incoming_raw.lower() in RESPONSES:
            await event.reply(RESPONSES[incoming_raw.lower()])
            return

        # ANTI-SPAM LIMIT
        current_time = time.time()
        if user_id in USER_LAST_MSG_TIME and (current_time - USER_LAST_MSG_TIME[user_id] < 10):
            return
        USER_LAST_MSG_TIME[user_id] = current_time

        # AFK MODE CHECK
        if AFK_MODE:
            await event.reply(f"🤖 **AFK Mode Active:** {AFK_REASON}")
            return

        # SMART AI AUTO-REPLY LOGIC (Skip if Owner is Online or Message is Read)
        if user_id not in REPLIED_USERS:
            # Wait 5 seconds to check if owner reads or replies manually
            await asyncio.sleep(5)
            
            # Check if event was read/seen by owner
            chat_state = await client.get_input_entity(event.chat_id)
            
            # If owner is online, skip AI reply so owner can manually reply
            if await is_owner_online():
                return

            if AI_REPLY_ENABLED and ai_client:
                try:
                    prompt = f"Briefly reply in Singlish to: '{incoming_raw}'"
                    response = ai_client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
                    await event.reply(f"{response.text.strip()}\n\n_(🤖 Auto Reply - Type !help for commands)_")
                except Exception:
                    pass
            REPLIED_USERS.add(user_id)

    except Exception as e:
        print(f"Public Handler Error: {e}")

# ---------------- FLASK & BOT START ----------------
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
