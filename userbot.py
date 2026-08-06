import json
import os
import re
import time
import asyncio
import threading
import logging
import uuid
from datetime import datetime
import pytz
import aiohttp
from flask import Flask
from telethon import TelegramClient, events
from bot_utils import extract_media_message, resolve_send_target
from telethon.sessions import StringSession
from telethon.errors import (
    UserIsBlockedError,
    PeerIdInvalidError,
    InputUserDeactivatedError,
    FloodWaitError,
    MessageNotModifiedError,
)
from google import genai

# ══════════════════════════════════════════════════════════════════════════
# 📖 FILE MAP — මේ file එකේ මොනවද කොහෙද කියලා ඉක්මනින් හොයාගන්න
#    (Ctrl+F කරලා පහළ තියෙන # 🔹 label එක search කරන්න)
# ══════════════════════════════════════════════════════════════════════════
#  🔹 CONFIGURATION              → API keys, model names, env vars ඔක්කොම
#  🔹 WORKING HOURS HELPER       → "!hours" feature එක actually check කරන logic
#  🔹 AI GENERATION HELPER       → Gemini API එකට call කරන function එක
#  🔹 DATA PERSISTENCE           → Storage Channel එකට save/load කරන logic
#  🔹 SAFE-SEND / SAFE-EDIT      → Telegram error handling (blocked/flood-wait)
#  🔹 OWNER COMMANDS             → ඔයා (owner) type කරන !commands ඔක්කොම
#      (!status, !afk, !hours, !add, !addmedia, !gcast, !reset ...)
#  🔹 PUBLIC HANDLER             → strangers/contacts bot එකට message කළාම
#      (welcome msg, !ask, !ytmp3, !exam, auto-reply, media-reply ...)
#  🔹 FLASK & STARTUP            → Render health-check server + bot start කිරීම
# ══════════════════════════════════════════════════════════════════════════

# Logging Configuration
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Userbot")

app = Flask(__name__)

@app.route('/')
def home():
    return "Userbot Utility Active & Alive!"

# ==================== 🔹 CONFIGURATION (Settings & API Keys) ====================

API_ID = 35039780              # Telegram App ID (my.telegram.org වලින්)
API_HASH = '4ec122e3bde00836e5a02223c5a7714d'   # Telegram App Hash
STORAGE_CHANNEL = -1004489211765  # ඔයාගේ private "My Bot Storage" channel ID —
                                   # settings/backup ඔක්කොම save වෙන්නේ මෙතනට
AL_EXAM_DATE = datetime(2028, 8, 10)  # Countdown එකට use කරන exam date එක

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")  # Render env var එකෙන් එනවා
ai_client = None

# ---- Gemini model fallback chain ----
# Google retires/renames Gemini model IDs every few months. Instead of a single
# hardcoded model name that will eventually 404 again, we try a short list of
# candidates in order. Override the primary via env var without touching code.
GEMINI_MODEL_CANDIDATES = [
    os.environ.get("GEMINI_MODEL", "gemini-3.5-flash"),
    "gemini-3.1-flash-lite",
]
GEMINI_MODEL_CANDIDATES = list(dict.fromkeys(GEMINI_MODEL_CANDIDATES))

if GEMINI_API_KEY:
    try:
        ai_client = genai.Client(api_key=GEMINI_API_KEY)
        logger.info("Gemini AI Client initialized successfully.")
    except Exception as e:
        logger.error(f"AI Client Setup Error: {e}")

# ---- Cobalt (YouTube downloader) instance config ----
# api.cobalt.tools blocks third-party/bot API usage and currently blocks
# YouTube downloads on its public instance. Self-host your own Cobalt instance
# (e.g. as a second free Render web service) and set these env vars:
#   COBALT_INSTANCE_URL = https://your-own-instance-url
#   COBALT_API_KEY      = (only if you enabled auth on your instance)
COBALT_INSTANCE_URL = os.environ.get("COBALT_INSTANCE_URL", "https://api.cobalt.tools/")
COBALT_API_KEY = os.environ.get("COBALT_API_KEY", "")
MAX_DOWNLOAD_MB = int(os.environ.get("MAX_DOWNLOAD_MB", "100"))

# How long (hours) before the AI auto-reply is allowed to fire again for the
# same user. Previously this was a permanent one-time-ever lock per user.
AUTO_REPLY_COOLDOWN_SECONDS = int(os.environ.get("AUTO_REPLY_COOLDOWN_HOURS", "6")) * 3600

session_str = os.environ.get("STRING_SESSION", "")
client = TelegramClient(StringSession(session_str), API_ID, API_HASH, sequential_updates=True)

DEFAULT_AFK_MSG = "මං පොඩි වැඩක ඉන්නේ. 💻 මේක Auto Reply එකක්, ආපු ගමන් මැසේජ් එකක් දාන්නම්..! ✨"

# ---- System Variables (bot එක run වෙද්දි memory එකේ තියෙන "state" එක) ----
# 👉 මේවා restart එකකදී ගිලිහෙන්නේ නෑ — DATA PERSISTENCE section එකෙන්
#    STORAGE_CHANNEL එකට save/load වෙනවා (ටිකක් පහළ බලන්න).
RESPONSES = {}          # !add එකෙන් හදන text auto-replies. e.g. {"hi": "hello!"}
MEDIA_RESPONSES = {}    # !addmedia එකෙන් හදන media auto-replies (key -> storage msg id)
IGNORED_USERS = set()   # !block කරපු chat/user id ලා — මේ අයට bot එක reply කරන්නේ නෑ
REPLIED_USERS = {}      # user_id -> අන්තිමට AI auto-reply කළ වෙලාව (cooldown track කරන්න)
KNOWN_CONTACTS = set()  # "!ask access" ලැබුණු අය (real contacts + welcome msg ලැබුණු අය)
BOT_BLOCKED_USERS = set()  # ඔයාගේ bot එක block කරපු Telegram users ලා
TODO_LIST = []          # !todo/!done වලින් manage කරන study targets list එක
USER_LAST_MSG_TIME = {} # spam වළක්වන්න, user කෙනෙක් message කරපු අන්තිම වෙලාව

AFK_MODE = False                # !afk on/off තියෙනවද
AFK_REASON = DEFAULT_AFK_MSG    # AFK message එකේ text එක
WORKING_HOURS_ONLY = False      # !hours on/off — යම් වෙලාවකදී විතරක් auto-reply active
START_HOUR = 1                  # Working hours range එකේ පටන් ගන්න පැය (Asia/Colombo)
END_HOUR = 7                    # Working hours range එකේ ඉවර වෙන පැය
WELCOME_MSG_ENABLED = True      # අලුත් කෙනෙක්ට එකපාරක් welcome msg යවනවද
AI_REPLY_ENABLED = True         # AI Auto Reply (passive) ON/OFF

# ==================== 🔹 WORKING HOURS HELPER (!hours feature එකේ logic) ====================
def is_within_working_hours():
    """Returns True if passive auto-replies (AFK/AI) should fire right now.
    Supports overnight ranges too, e.g. START_HOUR=22, END_HOUR=6."""
    if not WORKING_HOURS_ONLY:
        return True
    tz = pytz.timezone('Asia/Colombo')
    hour = datetime.now(tz).hour
    if START_HOUR <= END_HOUR:
        return START_HOUR <= hour < END_HOUR
    return hour >= START_HOUR or hour < END_HOUR

# ==================== 🔹 AI GENERATION HELPER (Gemini API call එක) ====================
async def generate_ai_response(prompt_text):
    if not ai_client:
        return "AI Client not initialized. (GEMINI_API_KEY missing)"

    last_error = None
    for model_name in GEMINI_MODEL_CANDIDATES:
        try:
            response = ai_client.models.generate_content(
                model=model_name,
                contents=prompt_text,
            )
            if response and response.text:
                return response.text.strip()
            last_error = "empty response"
        except Exception as e:
            err_str = str(e)
            logger.error(f"AI Generation Error ({model_name}): {err_str}")

            if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                return "QUOTA_EXCEEDED"

            if "404" in err_str or "NOT_FOUND" in err_str:
                last_error = err_str
                continue

            return f"Error: {err_str[:80]}"

    logger.error(f"All Gemini model candidates failed. Last error: {last_error}")
    return "MODEL_NOT_FOUND"

# ==================== 🔹 DATA PERSISTENCE (Storage Channel එකට Save/Load) ====================
# bot එක Render එකේ restart වුණාම (redeploy/crash/sleep) memory එකේ තිබුණු ඔක්කොම
# settings මැකෙනවා. ඒක වළක්වන්න, settings ටික JSON විදිහට STORAGE_CHANNEL එකට
# message එකක් විදිහට save කරලා, start වෙනකොට ආයෙත් load කරගන්නවා.
async def load_bot_data():
    global RESPONSES, MEDIA_RESPONSES, IGNORED_USERS, WORKING_HOURS_ONLY, START_HOUR, END_HOUR, WELCOME_MSG_ENABLED, KNOWN_CONTACTS, TODO_LIST, AI_REPLY_ENABLED, BOT_BLOCKED_USERS, AFK_MODE, AFK_REASON
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
                AFK_MODE = data.get("afk_mode", False)
                AFK_REASON = data.get("afk_reason", DEFAULT_AFK_MSG)
                TODO_LIST = data.get("todo_list", [])
                logger.info("Bot data loaded successfully from Storage Channel.")
                break
    except Exception as e:
        logger.error(f"Data Load Error: {e}")

async def save_bot_data():
    global RESPONSES, MEDIA_RESPONSES, IGNORED_USERS, WORKING_HOURS_ONLY, START_HOUR, END_HOUR, WELCOME_MSG_ENABLED, KNOWN_CONTACTS, TODO_LIST, AI_REPLY_ENABLED, BOT_BLOCKED_USERS, AFK_MODE, AFK_REASON
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
            "afk_mode": AFK_MODE,
            "afk_reason": AFK_REASON,
            "todo_list": TODO_LIST
        }
        text_to_save = f"[USERBOT_DATA_SAVE]\n{json.dumps(data, ensure_ascii=False)}"
        async for msg in client.iter_messages(STORAGE_CHANNEL, search="[USERBOT_DATA_SAVE]"):
            await msg.delete()
        await client.send_message(STORAGE_CHANNEL, text_to_save)
        logger.info("Bot data saved successfully.")
    except Exception as e:
        logger.error(f"Data Save Error: {e}")

# Helper: Decide if a user is allowed to use !ask (restricted feature).
# "Known" means either a real Telegram contact (owner already knows them), or
# someone who has already received the one-time welcome message before —
# i.e. not their very first-ever message to the bot.
def is_known_user(user_id, sender):
    is_contact = getattr(sender, 'contact', False)
    return bool(is_contact) or user_id in KNOWN_CONTACTS

# Helper: Check if account owner is online
async def is_owner_online():
    try:
        me = await client.get_me()
        return getattr(me.status, 'was_online', None) is None
    except Exception:
        return False

# Helper: Safely edit a message, falling back to a fresh send if the edit
# fails (e.g. edit window expired, or message untouched) instead of silently
# swallowing the error and leaving the user with no response at all.
async def safe_edit(msg_or_event, text):
    try:
        await msg_or_event.edit(text)
    except MessageNotModifiedError:
        pass
    except Exception as e:
        logger.warning(f"Edit failed ({e}); sending a new message instead.")
        try:
            await client.send_message(msg_or_event.chat_id, text)
        except Exception as ex2:
            logger.error(f"Fallback send also failed: {ex2}")

# Helper: Safely Send Message, Detect Blockers, and Handle Flood Waits
async def safe_send_message(entity, text, reply_to=None):
    target_type, target = resolve_send_target(entity, reply_to=reply_to)
    for attempt in range(2):
        try:
            if target_type == "reply":
                return await target.reply(text)
            if target_type == "chat":
                return await client.send_message(target, text)
            return await client.send_message(target, text)
        except FloodWaitError as fw:
            wait_s = min(fw.seconds, 60)
            logger.warning(f"FloodWait hit, sleeping {wait_s}s before retry.")
            await asyncio.sleep(wait_s)
            continue
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
            logger.warning(f"Message send failed with {target_type} target ({ex}); retrying with fallback target.")
            if target_type == "reply":
                target_type, target = resolve_send_target(entity, reply_to=None)
                continue
            logger.error(f"Message Send Error: {ex}")
            return None
    return None

# ==================== 🔹 OWNER COMMANDS (ඔයා type කරන !commands) ====================
# @client.on(events.NewMessage(outgoing=True)) කියන්නේ "ඔයා (account owner) විසින්
# යවන message" කියන එකයි. ඒ නිසා මේ function එක trigger වෙන්නේ ඔයා යවන
# !status, !afk, !add වගේ commands වලට විතරයි — වෙන කාටවත් නෙවෙයි.
@client.on(events.NewMessage(outgoing=True))
async def command_handler(event):
    global RESPONSES, MEDIA_RESPONSES, IGNORED_USERS, REPLIED_USERS, AFK_MODE, AFK_REASON, WORKING_HOURS_ONLY, START_HOUR, END_HOUR, WELCOME_MSG_ENABLED, KNOWN_CONTACTS, TODO_LIST, AI_REPLY_ENABLED, BOT_BLOCKED_USERS
    try:
        raw_text = event.raw_text.strip() if event.raw_text else ""
        if not raw_text:
            return

        if AFK_MODE and not raw_text.startswith("!afk"):
            AFK_MODE = False
            AFK_REASON = DEFAULT_AFK_MSG
            await save_bot_data()
            await client.send_message(STORAGE_CHANNEL, "🟢 **AFK Mode එක Off වුණා.**")

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
                "⚙️ **System Settings** _(මොකද කියලා පහළ බලන්න)_\n"
                f" ├ AFK Mode ➔ {'🟢 ON' if AFK_MODE else '🔴 OFF'} _(sent message වලට auto AFK reply)_\n"
                f" ├ Working Hours ➔ {'🟢 ON (' + str(START_HOUR) + ':00-' + str(END_HOUR) + ':00)' if WORKING_HOURS_ONLY else '🔴 OFF'} _(auto-reply active වෙන පැය)_\n"
                f" ├ Welcome Message ➔ {'🟢 ON' if WELCOME_MSG_ENABLED else '🔴 OFF'} _(අලුත් අයට එකපාරක් යවන msg)_\n"
                f" ├ AI Auto Reply ➔ {'🟢 ON' if AI_REPLY_ENABLED else '🔴 OFF'} _(AFK නැති වෙලාවක auto AI reply)_\n"
                f" ├ Custom Text Replies ➔ `{len(RESPONSES)} Units` _(!add එකෙන් හදපු ඒවා)_\n"
                f" ├ Custom Media Replies ➔ `{len(MEDIA_RESPONSES)} Units` _(!addmedia එකෙන් හදපු ඒවා)_\n"
                f" ├ Ignored / Bot Disabled Users ➔ `{len(IGNORED_USERS)} Users` _(ඔයා !block කරපු අය)_\n"
                f" └ Users Who Blocked Bot ➔ `{len(BOT_BLOCKED_USERS)} Users` _(ඔයාව Telegram එකේම block කරපු අය)_\n\n"
                f"📌 **Daily Study Targets**\n{todo_str}\n"
                "🤖 **Bot Commands** 👇\n\n"
                " ➦ `!status` - Dashboard & Countdown\n"
                " ➦ `!ignored` - ඔයා Bot ව Disable කරපු Users ලාගේ List එක\n"
                " ➦ `!blockedusers` - Bot එක Block කර ඇති අයගේ List එක\n"
                " ➦ `!todo <target>` - Target එකක් එකතු කිරීමට\n"
                " ➦ `!done <number>` - Target එක Complete කිරීමට\n"
                " ➦ `!cleartodo` - Targets Clear කිරීමට\n"
                " ➦ `!afk` / `!afk off` - Custom AFK Mode On/Off\n"
                " ➦ `!hours on` / `!hours off` - Working Hours\n"
                " ➦ `!hours range <start> <end>` - Working Hours Range Set කිරීමට\n"
                " ➦ `!welcome on` / `!welcome off` - Welcome Msg\n"
                " ➦ `!ai on` / `!ai off` - AI Auto Reply\n"
                " ➦ `!add word=reply` - Auto Reply එකතු කිරීමට\n"
                " ➦ `!addmedia word` - Media Auto Reply\n"
                " ➦ `!delmedia word` - Media Reply අයින් කිරීමට\n"
                " ➦ `!list` / `!listmedia` - Auto Replies ලැයිස්තුව\n"
                " ➦ `!block` / `!unblock` - Chat එකේදී Bot Disable/Enable කිරීමට\n"
                " ➦ `!gcast <msg>` - Message Broadcast\n"
                " ➦ `!reset` - Clear History & Contacts\n\n"
                "💡 **Pray to the Satan...! 🩸🖤**\n"
                "🚀 Status: Active & Operational"
            )
            await safe_edit(event, status_msg)
            return

        if raw_text in ["!ignored", "!blocklist"]:
            if not IGNORED_USERS:
                await safe_edit(event, "🟢 **ඔබ විසින් Bot ව වැඩ නොකරන ලෙස Block/Disable කළ අය කිසිවෙක් නැත.**")
                return

            await safe_edit(event, "🔍 **List එක සකස් කරමින් පවතී...**")
            msg = "🚫 **ඔබ විසින් Bot Disable / Block කළ Users ලැයිස්තුව:**\n\n"

            for u_id in list(IGNORED_USERS):
                try:
                    user_obj = await client.get_entity(u_id)
                    if getattr(user_obj, 'username', None):
                        msg += f"• @{user_obj.username} (`{u_id}`)\n"
                    else:
                        first_n = getattr(user_obj, 'first_name', 'User')
                        msg += f"• [{first_n}](tg://user?id={u_id}) (`{u_id}`)\n"
                except Exception:
                    msg += f"• User ID: `{u_id}`\n"

            await safe_edit(event, msg)
            return

        if raw_text == "!blockedusers":
            if not BOT_BLOCKED_USERS:
                await safe_edit(event, "🟢 **Bot/Userbot එක Block කළ අය කිසිවෙක් නැත.**")
                return
            msg = "🚫 **Bot එක Block කර ඇති Users ලැයිස්තුව:**\n\n"
            for u in BOT_BLOCKED_USERS:
                msg += f"• {u}\n"
            await safe_edit(event, msg)
            return

        if raw_text.startswith("!todo "):
            task = raw_text[6:].strip()
            if task:
                TODO_LIST.append(task)
                await save_bot_data()
                await safe_edit(event, f"✅ **Target එකතු කළා:** `{task}`")
            return

        if raw_text.startswith("!done "):
            try:
                idx = int(raw_text[6:].strip()) - 1
                if 0 <= idx < len(TODO_LIST):
                    removed = TODO_LIST.pop(idx)
                    await save_bot_data()
                    await safe_edit(event, f"🎉 **Target Completed:** `{removed}`")
                else:
                    await safe_edit(event, "❌ වැරදි අංකයකි.")
            except Exception:
                await safe_edit(event, "❌ Command එක වැරදියි. (e.g. `!done 1`)")
            return

        if raw_text == "!cleartodo":
            TODO_LIST.clear()
            await save_bot_data()
            await safe_edit(event, "🧹 **සියලුම Study Targets Clear කළා!**")
            return

        if raw_text.startswith("!afk"):
            arg = raw_text[4:].strip()
            if arg.lower() == "off":
                AFK_MODE = False
                AFK_REASON = DEFAULT_AFK_MSG
                await save_bot_data()
                await safe_edit(event, "🔴 **AFK Mode Off.**")
            else:
                AFK_REASON = arg if arg else DEFAULT_AFK_MSG
                AFK_MODE = True
                await save_bot_data()
                await safe_edit(event, f"🟢 **AFK Mode On!**\n\n💬 Message:\n\"{AFK_REASON}\"")
            return

        if raw_text.startswith("!hours"):
            arg = raw_text[6:].strip()
            parts = arg.split()
            if not parts:
                await safe_edit(event, "❌ Usage: `!hours on` / `!hours off` / `!hours range <start> <end>`")
                return
            sub = parts[0].lower()
            if sub == "on":
                WORKING_HOURS_ONLY = True
                await save_bot_data()
                await safe_edit(event, f"⚙️ **Working Hours:** `ON` (`{START_HOUR}:00 - {END_HOUR}:00`)")
            elif sub == "off":
                WORKING_HOURS_ONLY = False
                await save_bot_data()
                await safe_edit(event, "⚙️ **Working Hours:** `OFF`")
            elif sub == "range" and len(parts) == 3:
                try:
                    s, e = int(parts[1]), int(parts[2])
                    if 0 <= s <= 23 and 0 <= e <= 23:
                        START_HOUR, END_HOUR = s, e
                        await save_bot_data()
                        await safe_edit(event, f"⚙️ **Working Hours Range:** `{s}:00 - {e}:00` (Asia/Colombo)")
                    else:
                        await safe_edit(event, "❌ පැය 0-23 අතර දාන්න.")
                except ValueError:
                    await safe_edit(event, "❌ Usage: `!hours range <start_hour> <end_hour>` e.g. `!hours range 1 7`")
            else:
                await safe_edit(event, "❌ Usage: `!hours on` / `!hours off` / `!hours range <start> <end>`")
            return

        if raw_text.startswith("!welcome "):
            val = raw_text[9:].strip().lower()
            WELCOME_MSG_ENABLED = (val == "on")
            await save_bot_data()
            await safe_edit(event, f"⚙️ **Welcome Message:** `{'ON' if WELCOME_MSG_ENABLED else 'OFF'}`")
            return

        if raw_text.startswith("!ai "):
            val = raw_text[4:].strip().lower()
            AI_REPLY_ENABLED = (val == "on")
            await save_bot_data()
            await safe_edit(event, f"⚙️ **AI Auto Reply:** `{'ON' if AI_REPLY_ENABLED else 'OFF'}`")
            return

        if raw_text.startswith("!add ") and "=" in raw_text:
            parts = raw_text[5:].split("=", 1)
            key, val = parts[0].strip().lower(), parts[1].strip()
            RESPONSES[key] = val
            await save_bot_data()
            await safe_edit(event, f"✅ Auto Reply එකතු කළා: `{key}` ➔ `{val}`")
            return

        if raw_text.startswith("!del "):
            key = raw_text[5:].strip().lower()
            if key in RESPONSES:
                del RESPONSES[key]
                await save_bot_data()
                await safe_edit(event, f"🗑️ Auto reply අයින් කළා: `{key}`")
            return

        if raw_text == "!list":
            if not RESPONSES:
                await safe_edit(event, "📜 Text Auto Replies කිසිවක් නැත.")
                return
            msg = "📝 **Custom Text Replies:**\n\n"
            for k, v in RESPONSES.items():
                msg += f"• `{k}` ➔ {v}\n"
            await safe_edit(event, msg)
            return

        if raw_text.startswith("!addmedia "):
            key = raw_text[10:].strip().lower()
            reply_msg = await event.get_reply_message()
            if reply_msg and reply_msg.media:
                try:
                    # Forward the media into the storage channel itself so the
                    # stored message id is always resolvable later, regardless
                    # of which chat the original media came from (fixes media
                    # auto-replies never actually firing).
                    forwarded = await client.send_file(
                        STORAGE_CHANNEL,
                        reply_msg.media,
                        caption=f"[MEDIA_KEY:{key}]"
                    )
                    MEDIA_RESPONSES[key] = forwarded.id
                    await save_bot_data()
                    await safe_edit(event, f"🖼️ Media reply එකතු කළා for: `{key}`")
                except Exception as e:
                    logger.error(f"AddMedia Error: {e}")
                    await safe_edit(event, "❌ Media save කිරීමේදී error එකක් වුණා.")
            else:
                await safe_edit(event, "❌ Media Message එකකට Reply කර මේ Command එක දමන්න.")
            return

        if raw_text.startswith("!delmedia "):
            key = raw_text[10:].strip().lower()
            if key in MEDIA_RESPONSES:
                del MEDIA_RESPONSES[key]
                await save_bot_data()
                await safe_edit(event, f"🗑️ Media reply අයින් කළා: `{key}`")
            return

        if raw_text == "!listmedia":
            if not MEDIA_RESPONSES:
                await safe_edit(event, "🖼️ Custom Media Replies කිසිවක් නැත.")
                return
            msg = "🖼️ **Custom Media Replies:**\n\n"
            for k in MEDIA_RESPONSES.keys():
                msg += f"• `{k}`\n"
            await safe_edit(event, msg)
            return

        if raw_text in ["!block", "!unblock"]:
            chat = await event.get_chat()
            if event.is_private:
                if raw_text == "!block":
                    IGNORED_USERS.add(chat.id)
                    await save_bot_data()
                    await safe_edit(event, "🚫 **මේ Chat එක සඳහා Bot Disable කරන ලදී.**")
                else:
                    IGNORED_USERS.discard(chat.id)
                    await save_bot_data()
                    await safe_edit(event, "✅ **මේ Chat එක සඳහා Bot Enable කරන ලදී.**")
            return

        if raw_text.startswith("!gcast "):
            bc_msg = raw_text[7:].strip()
            if bc_msg:
                await safe_edit(event, "📢 **Broadcasting Message...**")
                sent_count = 0
                for user in list(KNOWN_CONTACTS):
                    res = await safe_send_message(user, bc_msg)
                    if res:
                        sent_count += 1
                    await asyncio.sleep(0.5)
                await safe_edit(event, f"✅ Broadcast Complete! Sent to `{sent_count}` users.")
            return

        if raw_text == "!reset":
            REPLIED_USERS.clear()
            KNOWN_CONTACTS.clear()
            BOT_BLOCKED_USERS.clear()
            await save_bot_data()
            await safe_edit(event, "🧹 **History, Contacts & Blocked List Cleared!**")
            return

    except Exception as e:
        logger.error(f"Owner Handler Error: {e}")

# ==================== 🔹 PUBLIC HANDLER (අනිත් අය message කළාම) ====================
# @client.on(events.NewMessage(incoming=True, ...)) කියන්නේ "අනිත් අය ඔයාට යවන
# message" කියන එකයි. Welcome message, !ask, !ytmp3, !exam, auto-reply — මේ
# ඔක්කොම logic එක මේ function එක ඇතුළේ.
@client.on(events.NewMessage(incoming=True, func=lambda e: e.is_private))
async def reply_handler(event):
    global REPLIED_USERS, IGNORED_USERS, AFK_MODE, AFK_REASON, WORKING_HOURS_ONLY, USER_LAST_MSG_TIME
    try:
        sender = await event.get_sender()
        user_id = event.sender_id
        if not user_id or user_id in IGNORED_USERS:
            return

        user_str = f"@{sender.username}" if sender and getattr(sender, 'username', None) else f"[{getattr(sender, 'first_name', 'User')}](tg://user?id={user_id})"
        if user_str in BOT_BLOCKED_USERS:
            BOT_BLOCKED_USERS.discard(user_str)
            await save_bot_data()

        incoming_raw = event.raw_text.strip() if event.raw_text else ""

        if user_id not in KNOWN_CONTACTS:
            try:
                is_bot = getattr(sender, 'bot', False)
                is_contact = getattr(sender, 'contact', False)
                if not is_bot:
                    if is_contact:
                        # Already a real Telegram contact — grant "known" status
                        # immediately, no need to send a welcome message.
                        KNOWN_CONTACTS.add(user_id)
                        await save_bot_data()
                    elif WELCOME_MSG_ENABLED:
                        welcome_text = (
                            "💌 **Hey! Thanks for your message.**\n"
                            "මම දැනට පොඩි වැඩක ඉන්නේ, ඉක්මනින්ම reply කරන්නම්! 😊\n\n"
                            "💡 **මෙතෙක් මගෙන් ලබාගත හැකි පහසුකම්:**\n"
                            " ➦ `!ask <ප්‍රශ්නය>` - A/L පාඩම් වල ඕනෑම ප්‍රශ්නයක් නිරාකරණය කරගන්න (ඊළඟ message එකේ ඉඳන්)\n"
                            " ➦ `!ytmp3 <Link>` - YouTube සින්දු MP3 විදිහට Download කරගන්න\n"
                            " ➦ `!help` - සියලුම Commands බලාගන්න"
                        )
                        await safe_send_message(event.chat_id, welcome_text, reply_to=event)
                        KNOWN_CONTACTS.add(user_id)
                        await save_bot_data()
            except Exception as ex:
                logger.error(f"Welcome Fetch Error: {ex}")

        if not incoming_raw:
            # Media-only message (sticker/photo/voice, no caption). Previously
            # the handler silently returned here with zero response at all —
            # now AFK still fires for these, respecting working hours.
            if AFK_MODE and is_within_working_hours():
                await safe_send_message(event.chat_id, AFK_REASON, reply_to=event)
            return

        if incoming_raw.lower() in ["!help", "/help", "help"]:
            help_text = (
                "🤖 **Assistant Public Commands:**\n\n"
                " ➦ `!ask <Question>` - Study ප්‍රශ්න වලට Step-by-Step විසඳුම් ලබාගන්න\n"
                " ➦ `!ytmp3 <YouTube Link>` - Audio Download කරගන්න\n"
                " ➦ `!exam` - A/L Exam Countdown එක බලන්න"
            )
            await safe_send_message(event.chat_id, help_text, reply_to=event)
            return

        if incoming_raw.lower() == "!exam":
            tz = pytz.timezone('Asia/Colombo')
            now = datetime.now(tz).replace(tzinfo=None)
            days_left = (AL_EXAM_DATE - now).days
            await safe_send_message(event.chat_id, f"🎯 **2028 A/L Exam එකට තව දින `{days_left}` ක් තියෙනවා!**\n\n_Good Luck with your Studies!_ 📚", reply_to=event)
            return

        if incoming_raw.lower().startswith("!ask "):
            if not is_known_user(user_id, sender):
                await safe_send_message(
                    event.chat_id,
                    "🔒 **මේ command එක දැනට ඔයාට use කරන්න බැහැ.**\n"
                    "ටිකක් ඉඳලා ආයෙත් message එකක් යවන්න, welcome message එකෙන් පස්සේ `!ask` access වෙනවා.",
                    reply_to=event
                )
                return
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
                        await safe_edit(status_msg, "⚠️ **AI API Quota Exceeded:** කරුණාකර අලුත් API Key එකක් Render එකට Update කරන්න.")
                    elif ai_text == "MODEL_NOT_FOUND":
                        await safe_edit(status_msg, "⚠️ **AI Model Unavailable:** Gemini model name එක deprecated වෙලා. GEMINI_MODEL env var එක check කරන්න.")
                    elif ai_text.startswith("Error:"):
                        await safe_edit(status_msg, f"⚠️ **AI Error:** {ai_text}")
                    elif ai_text:
                        await safe_edit(status_msg, f"📚 **Study Solution:**\n\n{ai_text}")
                    else:
                        await safe_edit(status_msg, "❌ උත්තරය සොයාගැනීමට නොහැකි විය.")
            elif not ai_client:
                await safe_send_message(event.chat_id, "⚠️ AI Client එක Setup වී නැත. GEMINI_API_KEY check කරන්න.", reply_to=event)
            return

        if incoming_raw.lower().startswith("!ytmp3 "):
            match = re.search(r'(https?://[^\s>]+)', incoming_raw)
            if match:
                url = match.group(1).rstrip('>')
            else:
                await safe_send_message(event.chat_id, "❌ **වැරදි Link එකකි!** කරුණාකර නිවැරදි YouTube URL එකක් ලබාදෙන්න.", reply_to=event)
                return

            if "youtube.com" in url or "youtu.be" in url:
                status_msg = await safe_send_message(event.chat_id, "📥 **YouTube MP3 Download වෙමින් පවතී...**", reply_to=event)
                # Unique filename per request — the old fixed "downloads/audio.mp3"
                # path meant two simultaneous requests from different users would
                # overwrite/corrupt each other's downloads.
                filepath = f"downloads/audio_{uuid.uuid4().hex}.mp3"
                try:
                    headers = {
                        "Accept": "application/json",
                        "Content-Type": "application/json",
                    }
                    if COBALT_API_KEY:
                        headers["Authorization"] = f"Api-Key {COBALT_API_KEY}"

                    payload = {
                        "url": url,
                        "downloadMode": "audio",
                        "audioFormat": "mp3",
                    }

                    dl_url = None
                    fail_reason = None

                    async with aiohttp.ClientSession() as session:
                        async with session.post(COBALT_INSTANCE_URL, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                            try:
                                res_json = await resp.json()
                            except Exception:
                                res_json = {}

                            status = res_json.get("status")
                            if resp.status == 200 and status in ("tunnel", "redirect"):
                                dl_url = res_json.get("url")
                            elif status == "picker":
                                items = res_json.get("picker", [])
                                if items:
                                    dl_url = items[0].get("url")
                            else:
                                fail_reason = res_json.get("error", {}).get("code") or f"HTTP {resp.status}"

                        if dl_url:
                            async with session.get(dl_url) as file_resp:
                                if file_resp.status != 200:
                                    fail_reason = f"file fetch HTTP {file_resp.status}"
                                else:
                                    content_length = file_resp.headers.get('Content-Length')
                                    if content_length and int(content_length) > MAX_DOWNLOAD_MB * 1024 * 1024:
                                        fail_reason = f"file too large ({int(content_length)//1024//1024}MB > {MAX_DOWNLOAD_MB}MB limit)"
                                    else:
                                        if status_msg:
                                            await safe_edit(status_msg, "⬆️ **Audio එක Telegram එකට Upload වෙමින් පවතී...**")
                                        os.makedirs("downloads", exist_ok=True)
                                        with open(filepath, "wb") as f:
                                            f.write(await file_resp.read())

                                        await client.send_file(event.chat_id, filepath, caption="🎵 **YouTube Audio Downloaded Successfully!**")
                                        if status_msg:
                                            try:
                                                await status_msg.delete()
                                            except Exception:
                                                pass
                                        return

                    if status_msg:
                        if COBALT_INSTANCE_URL.rstrip("/") == "https://api.cobalt.tools":
                            await safe_edit(
                                status_msg,
                                "❌ **Download Error:** Public Cobalt instance එක YouTube සහ third-party "
                                "bots block කරලා තියෙන්නේ. Self-hosted Cobalt instance එකක් setup කර "
                                "`COBALT_INSTANCE_URL` env var එක Render එකට දාන්න."
                            )
                        else:
                            await safe_edit(status_msg, f"❌ **Download Error:** {fail_reason or 'Audio එක ලබාගැනීමට නොහැකි විය.'}")

                except Exception as e:
                    logger.error(f"YT Download Error: {e}")
                    if status_msg:
                        await safe_edit(status_msg, "❌ **Download Error:** Server එක මගින් Download කිරීම අසාර්ථක විය.")
                finally:
                    if os.path.exists(filepath):
                        try:
                            os.remove(filepath)
                        except Exception:
                            pass
            return

        if incoming_raw.lower() in RESPONSES:
            await safe_send_message(event.chat_id, RESPONSES[incoming_raw.lower()], reply_to=event)
            return

        # Media auto-replies: this lookup didn't exist at all before, so
        # !addmedia entries were saved but NEVER actually sent to anyone.
        if incoming_raw.lower() in MEDIA_RESPONSES:
            stored_id = MEDIA_RESPONSES[incoming_raw.lower()]
            try:
                stored_msg = await client.get_messages(STORAGE_CHANNEL, ids=stored_id)
                stored_msg = extract_media_message(stored_msg)
                if stored_msg and getattr(stored_msg, "media", None):
                    await client.send_file(event.chat_id, stored_msg.media, reply_to=event.id)
                else:
                    logger.warning(f"Media response missing in storage channel for id={stored_id}")
            except Exception as e:
                logger.error(f"Media Reply Send Error: {e}")
            return

        current_time = time.time()
        if user_id in USER_LAST_MSG_TIME and (current_time - USER_LAST_MSG_TIME[user_id] < 10):
            return
        USER_LAST_MSG_TIME[user_id] = current_time

        if AFK_MODE:
            if is_within_working_hours():
                await safe_send_message(event.chat_id, AFK_REASON, reply_to=event)
            return

        last_replied = REPLIED_USERS.get(user_id, 0)
        if current_time - last_replied > AUTO_REPLY_COOLDOWN_SECONDS:
            await asyncio.sleep(5)

            if await is_owner_online():
                return

            if not is_within_working_hours():
                return

            if AI_REPLY_ENABLED and ai_client:
                prompt = f"Briefly reply in Singlish to: '{incoming_raw}'"
                ai_text = await generate_ai_response(prompt)
                if ai_text and ai_text not in ["QUOTA_EXCEEDED", "MODEL_NOT_FOUND"] and not ai_text.startswith("Error:"):
                    await safe_send_message(event.chat_id, f"{ai_text}\n\n_(🤖 Auto Reply - Type !help for commands)_", reply_to=event)
            REPLIED_USERS[user_id] = current_time

    except Exception as e:
        logger.error(f"Public Handler Error: {e}")

# ==================== 🔹 FLASK & STARTUP (Render health-check + Bot Start) ====================
# Render එකට "මේ service එක alive ද?" කියලා check කරන්න Flask web server
# එකක් ඕන (එහෙම නැත්නම් Render එක bot එක restart කරනවා). ඒක background
# thread එකක run කරලා, main thread එකේ Telegram bot එක run කරනවා.
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
