import json
import os
import re
import time
import asyncio
import threading
import logging
from datetime import datetime
import pytz
from flask import Flask
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.errors import UserIsBlockedError, PeerIdInvalidError, InputUserDeactivatedError
from google import genai
import yt_dlp

# Logging Configuration
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Userbot")

app = Flask(__name__)

@app.route('/')
def home():
    return "Userbot Utility Active & Alive!"

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
        logger.info("Gemini AI Client initialized successfully.")
    except Exception as e:
        logger.error(f"AI Client Setup Error: {e}")

session_str = os.environ.get("STRING_SESSION", "")
client = TelegramClient(StringSession(session_str), API_ID, API_HASH, sequential_updates=True)

DEFAULT_AFK_MSG = "මං පොඩි වැඩක ඉන්නේ. 💻 මේක Auto Reply එකක්, ආපු ගමන් මැසේජ් එකක් දාන්නම්..! ✨"

# System Variables
RESPONSES = {}
MEDIA_RESPONSES = {}
IGNORED_USERS = set()
REPLIED_USERS = set()
KNOWN_CONTACTS = set()
BOT_BLOCKED_USERS = set()
TODO_LIST = []
USER_LAST_MSG_TIME = {}

AFK_MODE = False
AFK_REASON = DEFAULT_AFK_MSG
WORKING_HOURS_ONLY = False
START_HOUR = 1
END_HOUR = 7
WELCOME_MSG_ENABLED = True
AI_REPLY_ENABLED = True

# ---------------- HELPER FOR AI GENERATION ----------------
async def generate_ai_response(prompt_text):
    """ Tries to generate AI response with fallback models & error handling """
    if not ai_client:
        return None
    
    # List of models to attempt in order
    models_to_try = ['gemini-2.5-flash', 'gemini-2.0-flash']
    
    for model_name in models_to_try:
        try:
            response = ai_client.models.generate_content(
                model=model_name,
                contents=prompt_text,
            )
            if response and response.text:
                return response.text.strip()
        except Exception as e:
            err_str = str(e)
            logger.warning(f"Failed with {model_name}: {err_str}")
            if "429" in err_str:
                return "QUOTA_EXCEEDED"
            continue
            
    return None

# ---------------- DATA PERSISTENCE ----------------
async def load_bot_data():
    global RESPONSES, MEDIA_RESPONSES, IGNORED_USERS, WORKING_HOURS_ONLY, START_HOUR, END_HOUR, WELCOME_MSG_ENABLED, KNOWN_CONTACTS, TODO_LIST, AI_REPLY_ENABLED, BOT_BLOCKED_USERS
    try:
        async for msg in client.iter_messages(STORAGE_CHANNEL, search="[USERBOT_DATA_SAVE]"):
            if msg.text and "[USERBOT_DATA_SAVE]" in msg.text:
                json_str = msg.text.split("[USERBOT_DATA_SAVE]")[1].strip()
                data = json.loads(json_str)
                RESPONSES = data.get("responses", {})
                MEDIA_RESPONSES = data.get("media_responses", {})
                IGNORED_USERS = set(data.get("ignored", []))
                KNOWN_CONTACTS = set(data.get("known_contacts", []))
                BOT_BLOCKED_USERS = set(data.get("bot_blocked_users", []))
                WORKING_HOURS_ONLY = data.get("working_hours", False)
                START_HOUR = data.get("start_hour", 1)
                END_HOUR = data.get("end_hour", 7)
                WELCOME_MSG_ENABLED = data.get("welcome_msg", True)
                AI_REPLY_ENABLED = data.get("ai_reply", True)
                TODO_LIST = data.get("todo_list", [])
                logger.info("Bot data loaded successfully from Storage Channel.")
                break
    except Exception as e:
        logger.error(f"Data Load Error: {e}")

async def save_bot_data():
    global RESPONSES, MEDIA_RESPONSES, IGNORED_USERS, WORKING_HOURS_ONLY, START_HOUR, END_HOUR, WELCOME_MSG_ENABLED, KNOWN_CONTACTS, TODO_LIST, AI_REPLY_ENABLED, BOT_BLOCKED_USERS
    try:
        data = {
            "responses": RESPONSES,
            "media_responses": MEDIA_RESPONSES,
            "ignored": list(IGNORED_USERS),
            "known_contacts": list(KNOWN_CONTACTS),
            "bot_blocked_users": list(BOT_BLOCKED_USERS),
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
        logger.info("Bot data saved successfully.")
    except Exception as e:
        logger.error(f"Data Save Error: {e}")

# Helper: Check if account owner is online
async def is_owner_online():
    try:
        me = await client.get_me()
        return getattr(me.status, 'was_online', None) is None
    except Exception:
        return False

# Helper: Safely Send Message and Detect Blockers
async def safe_send_message(entity, text, reply_to=None):
    try:
        if reply_to:
            return await reply_to.reply(text)
        else:
            return await client.send_message(entity, text)
    except (UserIsBlockedError, InputUserDeactivatedError, PeerIdInvalidError):
        user_identifier = str(entity)
        try:
            user_obj = await client.get_entity(entity)
            user_identifier = f"@{user_obj.username}" if user_obj.username else f"[{user_obj.first_name}](tg://user?id={user_obj.id})"
        except Exception:
            pass
        
        if user_identifier not in BOT_BLOCKED_USERS:
            BOT_BLOCKED_USERS.add(user_identifier)
            await save_bot_data()
            logger.warning(f"Detected Blocked User: {user_identifier}")
            await client.send_message(STORAGE_CHANNEL, f"🚫 **User Blocked Bot Detected!**\n\n👤 User: {user_identifier}")
        return None
    except Exception as ex:
        logger.error(f"Message Send Error: {ex}")
        return None

# ---------------- OWNER COMMANDS (OUTGOING) ----------------
@client.on(events.NewMessage(outgoing=True))
async def command_handler(event):
    global RESPONSES, MEDIA_RESPONSES, IGNORED_USERS, REPLIED_USERS, AFK_MODE, AFK_REASON, WORKING_HOURS_ONLY, WELCOME_MSG_ENABLED, KNOWN_CONTACTS, TODO_LIST, AI_REPLY_ENABLED, BOT_BLOCKED_USERS
    try:
        raw_text = event.raw_text.strip() if event.raw_text else ""
        if not raw_text:
            return

        # Auto Turn-Off AFK when owner sends a message
        if AFK_MODE and not raw_text.startswith("!afk"):
            AFK_MODE = False
            AFK_REASON = DEFAULT_AFK_MSG
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
                "👋 **Hello, Satan!**\n\n"
                f"🎯 **A/L Exam Countdown (2028-08-10)**\n"
                f" └ `{days_left} Days Remaining!`\n\n"
                "⚙️ **System Settings**\n"
                f" ├ AFK Mode ➔ {'🟢 ON' if AFK_MODE else '🔴 OFF'}\n"
                f" ├ Working Hours ➔ {'🟢 ON' if WORKING_HOURS_ONLY else '🔴 OFF'}\n"
                f" ├ Welcome Message ➔ {'🟢 ON' if WELCOME_MSG_ENABLED else '🔴 OFF'}\n"
                f" ├ Custom Text Replies ➔ `{len(RESPONSES)} Units`\n"
                f" ├ Custom Media Replies ➔ `{len(MEDIA_RESPONSES)} Units`\n"
                f" ├ Users Who Blocked Bot ➔ `{len(BOT_BLOCKED_USERS)} Users`\n"
                f" └ Blocked Users ➔ `{len(IGNORED_USERS)} Users`\n\n"
                f"📌 **Daily Study Targets**\n{todo_str}\n"
                "🤖 **Bot Commands** 👇\n\n"
                " ➦ `!status` - Dashboard & Countdown\n"
                " ➦ `!blockedusers` - Bot එක Block කර ඇති අයගේ List එක\n"
                " ➦ `!todo <target>` - Target එකක් එකතු කිරීමට\n"
                " ➦ `!done <number>` - Target එක Complete කිරීමට\n"
                " ➦ `!cleartodo` - Targets Clear කිරීමට\n"
                " ➦ `!afk` / `!afk off` - Custom AFK Mode On/Off\n"
                " ➦ `!hours on` / `!hours off` - Working Hours\n"
                " ➦ `!welcome on` / `!welcome off` - Welcome Msg\n"
                " ➦ `!add word=reply` - Auto Reply එකතු කිරීමට\n"
                " ➦ `!addmedia word` - Media Auto Reply\n"
                " ➦ `!delmedia word` - Media Reply අයින් කිරීමට\n"
                " ➦ `!list` / `!listmedia` - Auto Replies ලැයිස්තුව\n"
                " ➦ `!block` / `!unblock` - Block/Unblock Chat\n"
                " ➦ `!gcast <msg>` - Message Broadcast\n"
                " ➦ `!reset` - Clear History & Contacts\n\n"
                "💡 **Pray to the Satan...! 🩸🖤**\n"
                "🚀 Status: Active & Operational"
            )
            await event.edit(status_msg)
            return

        # 2. CHECK BLOCKED USERS COMMAND
        if raw_text == "!blockedusers":
            if not BOT_BLOCKED_USERS:
                await event.edit("🟢 **Bot/Userbot එක Block කළ අය කිසිවෙක් නැත.**")
                return
            msg = "🚫 **Bot එක Block කර ඇති Users ලැයිස්තුව:**\n\n"
            for u in BOT_BLOCKED_USERS:
                msg += f"• {u}\n"
            await event.edit(msg)
            return

        # 3. TODO TARGET COMMANDS
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

        # 4. AFK COMMAND
        if raw_text.startswith("!afk"):
            arg = raw_text[4:].strip()
            if arg.lower() == "off":
                AFK_MODE = False
                AFK_REASON = DEFAULT_AFK_MSG
                await event.edit("🔴 **AFK Mode Off.**")
            else:
                AFK_REASON = arg if arg else DEFAULT_AFK_MSG
                AFK_MODE = True
                await event.edit(f"🟢 **AFK Mode On!**\n\n💬 Message:\n\"{AFK_REASON}\"")
            return

        # 5. SYSTEM TOGGLES
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

        # 6. CUSTOM REPLIES
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

        # 7. MEDIA REPLIES
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
                await event.edit("🖼️ Custom Media Replies කිසිවක් නැත.")
                return
            msg = "🖼️ **Custom Media Replies:**\n\n"
            for k in MEDIA_RESPONSES.keys():
                msg += f"• `{k}`\n"
            await event.edit(msg)
            return

        # 8. BLOCK & UNBLOCK
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

        # 9. BROADCAST (!gcast)
        if raw_text.startswith("!gcast "):
            bc_msg = raw_text[7:].strip()
            if bc_msg:
                await event.edit("📢 **Broadcasting Message...**")
                sent_count = 0
                for user in list(KNOWN_CONTACTS):
                    res = await safe_send_message(user, bc_msg)
                    if res:
                        sent_count += 1
                    await asyncio.sleep(0.5)
                await event.edit(f"✅ Broadcast Complete! Sent to `{sent_count}` users.")
            return

        # 10. RESET HISTORY
        if raw_text == "!reset":
            REPLIED_USERS.clear()
            KNOWN_CONTACTS.clear()
            BOT_BLOCKED_USERS.clear()
            await save_bot_data()
            await event.edit("🧹 **History, Contacts & Blocked List Cleared!**")
            return

    except Exception as e:
        logger.error(f"Owner Handler Error: {e}")

# ---------------- PUBLIC & INCOMING HANDLER ----------------
@client.on(events.NewMessage(incoming=True, func=lambda e: e.is_private))
async def reply_handler(event):
    global REPLIED_USERS, IGNORED_USERS, AFK_MODE, AFK_REASON, WORKING_HOURS_ONLY, USER_LAST_MSG_TIME
    try:
        sender = await event.get_sender()
        user_id = event.sender_id
        if not user_id or user_id in IGNORED_USERS:
            return

        # Unblock check
        user_str = f"@{sender.username}" if sender and getattr(sender, 'username', None) else f"[{getattr(sender, 'first_name', 'User')}](tg://user?id={user_id})"
        if user_str in BOT_BLOCKED_USERS:
            BOT_BLOCKED_USERS.discard(user_str)
            await save_bot_data()

        incoming_raw = event.raw_text.strip() if event.raw_text else ""

        # WELCOME MESSAGE FOR NEW CONTACTS
        if WELCOME_MSG_ENABLED and user_id not in KNOWN_CONTACTS:
            try:
                is_bot = getattr(sender, 'bot', False)
                is_contact = getattr(sender, 'contact', False)
                if not is_contact and not is_bot:
                    welcome_text = (
                        "💌 **Hey! Thanks for your message.**\n"
                        "මම දැනට පොඩි වැඩක ඉන්නේ, ඉක්මනින්ම reply කරන්නම්! 😊\n\n"
                        "💡 **මෙතෙක් මගෙන් ලබාගත හැකි පහසුකම්:**\n"
                        " ➦ `!ask <ප්‍රශ්නය>` - A/L පාඩම් වල ඕනෑම ප්‍රශ්නයක් නිරාකරණය කරගන්න\n"
                        " ➦ `!ytmp3 <Link>` - YouTube සින්දු MP3 විදිහට Download කරගන්න\n"
                        " ➦ `!help` - සියලුම Commands බලාගන්න"
                    )
                    await safe_send_message(event.chat_id, welcome_text, reply_to=event)
                    KNOWN_CONTACTS.add(user_id)
                    await save_bot_data()
            except Exception as ex:
                logger.error(f"Welcome Fetch Error: {ex}")

        if not incoming_raw:
            return

        # PUBLIC COMMAND 1: HELP
        if incoming_raw.lower() in ["!help", "/help", "help"]:
            help_text = (
                "🤖 **Assistant Public Commands:**\n\n"
                " ➦ `!ask <Question>` - Study ප්‍රශ්න වලට Step-by-Step විසඳුම් ලබාගන්න\n"
                " ➦ `!ytmp3 <YouTube Link>` - Audio Download කරගන්න\n"
                " ➦ `!exam` - A/L Exam Countdown එක බලන්න"
            )
            await safe_send_message(event.chat_id, help_text, reply_to=event)
            return

        # PUBLIC COMMAND 2: A/L COUNTDOWN
        if incoming_raw.lower() == "!exam":
            tz = pytz.timezone('Asia/Colombo')
            now = datetime.now(tz).replace(tzinfo=None)
            days_left = (AL_EXAM_DATE - now).days
            await safe_send_message(event.chat_id, f"🎯 **2028 A/L Exam එකට තව දින `{days_left}` ක් තියෙනවා!**\n\n_Good Luck with your Studies!_ 📚", reply_to=event)
            return

        # PUBLIC COMMAND 3: GENERAL STUDY HELPER (!ask)
        if incoming_raw.lower().startswith("!ask "):
            query = incoming_raw[5:].strip()
            if ai_client and query:
                status_msg = await safe_send_message(event.chat_id, "🧠 **ප්‍රශ්නය විශ්ලේෂණය කරමින් පවතී...**", reply_to=event)
                prompt = (
                    f"You are an expert A/L tutor (Maths, Physics, Chemistry, etc.). "
                    f"Solve or explain this question clearly step-by-step in Sinhala/Singlish: '{query}'"
                )
                ai_text = await generate_ai_response(prompt)
                
                if status_msg:
                    if ai_text == "QUOTA_EXCEEDED":
                        await status_msg.edit("⚠️ **AI Server Busy (Quota Limit):** විනාඩියකින් නැවත උත්සාහ කරන්න.")
                    elif ai_text:
                        await status_msg.edit(f"📚 **Study Solution:**\n\n{ai_text}")
                    else:
                        await status_msg.edit("❌ උත්තරය සොයාගැනීමට නොහැකි විය. කරුණාකර ප්‍රශ්නය පැහැදිලිව යොමු කරන්න.")
            return

        # PUBLIC COMMAND 4: YOUTUBE MP3 DOWNLOADER
        if incoming_raw.lower().startswith("!ytmp3 "):
            url = incoming_raw[7:].strip()
            if "youtube.com" in url or "youtu.be" in url:
                status_msg = await safe_send_message(event.chat_id, "📥 **YouTube MP3 Download වෙමින් පවතී...**", reply_to=event)
                try:
                    ydl_opts = {
                        'format': 'bestaudio/best',
                        'outtmpl': 'downloads/%(id)s.%(ext)s',
                        'max_filesize': 50 * 1024 * 1024,
                    }
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(url, download=True)
                        filename = ydl.prepare_filename(info)

                    if status_msg:
                        await status_msg.edit("⬆️ **Audio එක Telegram එකට Upload වෙමින් පවතී...**")
                    await client.send_file(event.chat_id, filename, caption=f"🎵 **{info.get('title')}**\n\nDownloaded via Assistant Bot")
                    if status_msg:
                        await status_msg.delete()
                    if os.path.exists(filename):
                        os.remove(filename)
                except Exception:
                    if status_msg:
                        await status_msg.edit("❌ **Download Error:** File එක විශාල වැඩියි හෝ Link එක වැරදියි.")
            return

        # CHECK CUSTOM TEXT REPLIES
        if incoming_raw.lower() in RESPONSES:
            await safe_send_message(event.chat_id, RESPONSES[incoming_raw.lower()], reply_to=event)
            return

        # ANTI-SPAM LIMIT
        current_time = time.time()
        if user_id in USER_LAST_MSG_TIME and (current_time - USER_LAST_MSG_TIME[user_id] < 10):
            return
        USER_LAST_MSG_TIME[user_id] = current_time

        # AFK MODE CHECK
        if AFK_MODE:
            await safe_send_message(event.chat_id, AFK_REASON, reply_to=event)
            return

        # SMART AI AUTO-REPLY LOGIC
        if user_id not in REPLIED_USERS:
            await asyncio.sleep(5)
            
            if await is_owner_online():
                return

            if AI_REPLY_ENABLED and ai_client:
                prompt = f"Briefly reply in Singlish to: '{incoming_raw}'"
                ai_text = await generate_ai_response(prompt)
                if ai_text and ai_text != "QUOTA_EXCEEDED":
                    await safe_send_message(event.chat_id, f"{ai_text}\n\n_(🤖 Auto Reply - Type !help for commands)_", reply_to=event)
            REPLIED_USERS.add(user_id)

    except Exception as e:
        logger.error(f"Public Handler Error: {e}")

# ---------------- FLASK & BOT ASYNC START ----------------
def run_flask():
    port = int(os.environ.get("PORT", 10000))
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)
    app.run(host="0.0.0.0", port=port, use_reloader=False)

async def main():
    logger.info("Starting Telethon Client...")
    await client.start()
    logger.info("Userbot Logged In Successfully!")
    
    await load_bot_data()
    try:
        await client.send_message(STORAGE_CHANNEL, "🚀 **Userbot Successfully Deployed & Updated!**\n\n_System is active and ready to operate._ 🖤")
    except Exception as e:
        logger.error(f"Startup Notification Error: {e}")

    await client.run_until_disconnected()

if __name__ == "__main__":
    t = threading.Thread(target=run_flask)
    t.daemon = True
    t.start()
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
