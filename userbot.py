import json
import os
import re
import time
import threading
from datetime import datetime
import pytz
from flask import Flask
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.functions.users import GetFullUserRequest
import google.generativeai as genai

app = Flask(__name__)

@app.route('/')
def home():
    return "Userbot is Live & Upgraded!"

# Telegram API Setup
api_id = 35039780
api_hash = '4ec122e3bde00836e5a02223c5a7714d'

# Gemini AI Integration (Fetch safely from Environment Variable)
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
try:
    if GEMINI_API_KEY:
        genai.configure(api_key=GEMINI_API_KEY)
        ai_model = genai.GenerativeModel('gemini-1.5-flash')
    else:
        ai_model = None
except Exception as e:
    ai_model = None
    print(f"AI Setup Error: {e}")

STORAGE_CHANNEL = -1004489211765
AL_EXAM_DATE = datetime(2028, 8, 10)

session_str = os.environ.get("STRING_SESSION", "")
client = TelegramClient(StringSession(session_str), api_id, api_hash, sequential_updates=True)

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

@client.on(events.NewMessage(outgoing=True))
async def command_handler(event):
    global RESPONSES, MEDIA_RESPONSES, IGNORED_USERS, REPLIED_USERS, AFK_MODE, AFK_REASON, WORKING_HOURS_ONLY, START_HOUR, END_HOUR, WELCOME_MSG_ENABLED, KNOWN_CONTACTS, TODO_LIST, AI_REPLY_ENABLED
    try:
        raw_text = event.raw_text.strip() if event.raw_text else ""
        if not raw_text:
            return

        lines = raw_text.split('\n')
        added_count = 0

        if AFK_MODE and not raw_text.startswith("!afk"):
            AFK_MODE = False
            AFK_REASON = ""
            await client.send_message(STORAGE_CHANNEL, "🟢 **AFK Mode Turn Off විය.**")

        # DASHBOARD COMMAND
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
                "👋 **Hello Satan!**\n\n"
                f"🎯 **A/L Exam Countdown (2028-08-10)**\n"
                f" └ `{days_left} Days Remaining!`\n\n"
                "⚙️ **System Settings**\n"
                f" ├ AFK Mode ➔ {'🟢 ON' if AFK_MODE else '🔴 OFF'}\n"
                f" ├ Working Hours ➔ {'🟢 ON' if WORKING_HOURS_ONLY else '🔴 OFF'} ({START_HOUR}:00 - {END_HOUR}:00)\n"
                f" ├ Welcome Message ➔ {'🟢 ON' if WELCOME_MSG_ENABLED else '🔴 OFF'}\n"
                f" ├ Smart AI Replies ➔ {'🟢 ON' if AI_REPLY_ENABLED else '🔴 OFF'}\n"
                f" ├ Custom Text Replies ➔ `{len(RESPONSES)}` Units\n"
                f" ├ Custom Media Replies ➔ `{len(MEDIA_RESPONSES)}` Units\n"
                f" └ Blocked Users ➔ `{len(IGNORED_USERS)}` Users\n\n"
                "📌 **Daily Study Targets**\n"
                f"{todo_str}\n"
                "🤖 **Bot Commands** 👇\n\n"
                " ➦ `!status` - Dashboard\n"
                " ➦ `!todo <target>` | `!done <num>` | `!cleartodo`\n"
                " ➦ `!afk <reason>` / `!afk off` - AFK Mode\n"
                " ➦ `!hours on <start>-<end>` / `!hours off` - Quiet Time\n"
                " ➦ `!welcome on` / `!welcome off` - Welcome Msg\n"
                " ➦ `!ai on` / `!ai off` - Gemini AI Auto-reply\n"
                " ➦ `!add word=reply` | `!del word` | `!list`\n"
                " ➦ `!addmedia word` | `!delmedia word` | `!listmedia`\n"
                " ➦ `!block` / `!unblock` / `!blocklist`\n"
                " ➦ `!gcast <msg>` | `!reset` - Clear History\n\n"
                "> 🩸🖤 **Pray to the Satan...!**\n"
                "> 🚀 Status: Upgraded & Operational"
            )
            await event.edit(status_msg)
            return

        # AI CONTROL
        if raw_text.startswith("!ai "):
            arg = raw_text[4:].strip().lower()
            if arg == "on":
                AI_REPLY_ENABLED = True
                await save_bot_data()
                await event.edit("🟢 **Gemini AI Auto-reply ON කරන ලදී.**")
            elif arg == "off":
                AI_REPLY_ENABLED = False
                await save_bot_data()
                await event.edit("🔴 **Gemini AI Auto-reply OFF කරන ලදී.**")
            return

        # WORKING HOURS CONTROL
        if raw_text.startswith("!hours"):
            args = raw_text[6:].strip().split()
            if args and args[0].lower() == "off":
                WORKING_HOURS_ONLY = False
                await save_bot_data()
                await event.edit("🔴 **Working Hours Restriction Off විය.**")
            elif args and args[0].lower() == "on":
                WORKING_HOURS_ONLY = True
                if len(args) > 1 and "-" in args[1]:
                    try:
                        s, e = args[1].split("-")
                        START_HOUR, END_HOUR = int(s), int(e)
                    except:
                        pass
                await save_bot_data()
                await event.edit(f"🟢 **Working Hours Mode On විය! (Quiet Time: {START_HOUR}:00 - {END_HOUR}:00)**")
            return

        # TODO COMMANDS
        if raw_text.startswith("!todo "):
            task = raw_text[6:].strip()
            if task:
                TODO_LIST.append(task)
                await save_bot_data()
                await event.edit(f"📚 **Study Target එකතු කළා:** `{task}`")
            return

        if raw_text.startswith("!done "):
            try:
                task_num = int(raw_text[6:].strip())
                if 1 <= task_num <= len(TODO_LIST):
                    removed = TODO_LIST.pop(task_num - 1)
                    await save_bot_data()
                    await event.edit(f"✅ **Target Completed!** ~`{removed}`~")
                else:
                    await event.edit("❌ **වැරදි අංකයකි.**")
            except ValueError:
                await event.edit("❌ **අංකයක් ඇතුළත් කරන්න.**")
            return

        if raw_text == "!cleartodo":
            TODO_LIST.clear()
            await save_bot_data()
            await event.edit("🗑️ **සියලුම Study Targets මකා දැමීය.**")
            return

        # AFK
        if raw_text.startswith("!afk"):
            arg = raw_text[4:].strip()
            if arg.lower() == "off":
                AFK_MODE = False
                AFK_REASON = ""
                await event.edit("🔴 **AFK Mode Off කරන ලදී.**")
            else:
                AFK_REASON = arg or "වැඩක ඉන්නේ."
                AFK_MODE = True
                await event.edit(f"🟢 **AFK Mode On විය!**\n හේතුව: `{AFK_REASON}`")
            return

        # WELCOME
        if raw_text.startswith("!welcome "):
            arg = raw_text[9:].strip().lower()
            if arg == "on":
                WELCOME_MSG_ENABLED = True
                await save_bot_data()
                await event.edit("🟢 **Welcome Message ON කරන ලදී.**")
            elif arg == "off":
                WELCOME_MSG_ENABLED = False
                await save_bot_data()
                await event.edit("🔴 **Welcome Message OFF කරන ලදී.**")
            return

        # MEDIA REPLIES
        if raw_text.startswith("!addmedia ") and event.is_reply:
            word = raw_text[10:].strip().lower()
            reply_msg = await event.get_reply_message()
            if reply_msg and word:
                MEDIA_RESPONSES[word] = reply_msg.id
                await save_bot_data()
                await event.edit(f"🖼️ **Media Auto-Reply එකතු කළා (`{word}`)!**")
            return

        if raw_text.startswith("!delmedia "):
            word = raw_text[10:].strip().lower()
            if word in MEDIA_RESPONSES:
                del MEDIA_RESPONSES[word]
                await save_bot_data()
                await event.edit(f"🗑️ Media Auto-Reply `{word}` **අයින් කළා.**")
            return

        if raw_text == "!listmedia":
            if not MEDIA_RESPONSES:
                await event.edit("📝 **Media Auto Replies කිසිවක් නැත.**")
                return
            msg = f"🖼️ **Media Auto Replies ({len(MEDIA_RESPONSES)}):**\n\n"
            for w in MEDIA_RESPONSES.keys():
                msg += f"• `{w}` ➔ 🖼️ [Saved Media]\n"
            await event.edit(msg)
            return

        # GCAST & BLOCK
        if raw_text.startswith("!gcast "):
            msg_to_send = raw_text[7:].strip()
            await event.edit("📢 **Broadcasting Message...**")
            dialogs = await client.get_dialogs()
            sent_count = 0
            for dialog in dialogs:
                if dialog.is_user and not dialog.entity.bot and dialog.id not in IGNORED_USERS:
                    try:
                        await client.send_message(dialog.id, msg_to_send)
                        sent_count += 1
                    except Exception:
                        pass
            await event.edit(f"✅ **Broadcast Done! Messages {sent_count} කට යැවීය.**")
            return

        if (raw_text in ["!block", "!nobot"]) and event.is_reply:
            reply_msg = await event.get_reply_message()
            user_id = reply_msg.sender_id
            me = await client.get_me()
            if user_id != me.id:
                IGNORED_USERS.add(user_id)
                await save_bot_data()
                await event.edit("✅ **User Blocked.**")
            return

        if raw_text == "!unblock" and event.is_reply:
            reply_msg = await event.get_reply_message()
            user_id = reply_msg.sender_id
            if user_id in IGNORED_USERS:
                IGNORED_USERS.remove(user_id)
                await save_bot_data()
                await event.edit("✅ **User Unblocked.**")
            return

        # MULTI ADD TEXT REPLIES
        for line in lines:
            line = line.strip()
            if line.startswith("!add "):
                try:
                    content = line[5:]
                    if "=" in content:
                        word, reply = content.split("=", 1)
                        word, reply = word.strip().lower(), reply.strip()
                        if word:
                            RESPONSES[word] = reply
                            added_count += 1
                except Exception:
                    pass

        if added_count > 0:
            await save_bot_data()
            await event.edit(f"✅ **Auto Replies {added_count}ක් එකතු කළා!**")
            return

        if raw_text.startswith("!del "):
            word = raw_text[5:].strip().lower()
            RESPONSES.pop(word, None)
            MEDIA_RESPONSES.pop(word, None)
            await save_bot_data()
            await event.edit(f"🗑️ `{word}` **අයින් කළා.**")

        elif raw_text == "!clear":
            RESPONSES.clear()
            MEDIA_RESPONSES.clear()
            await save_bot_data()
            await event.edit("🗑️ **සියලුම Auto Replies මකා දැමීය!**")

        elif raw_text == "!list":
            msg = f"📝 **Auto Replies ({len(RESPONSES) + len(MEDIA_RESPONSES)}):**\n\n"
            for w, r in RESPONSES.items():
                msg += f"• `{w}` ➔ {r}\n"
            for w in MEDIA_RESPONSES.keys():
                msg += f"• `{w}` ➔ 🖼️ [Media Response]\n"
            await event.edit(msg if (RESPONSES or MEDIA_RESPONSES) else "📝 **ලැයිස්තුව හිස්ය.**")

        elif raw_text == "!reset":
            REPLIED_USERS.clear()
            KNOWN_CONTACTS.clear()
            await save_bot_data()
            await event.edit("🔄 **History Reset කළා!**")

    except Exception:
        pass

# INCOMING MESSAGE HANDLER
@client.on(events.NewMessage(incoming=True, func=lambda e: e.is_private))
async def reply_handler(event):
    global REPLIED_USERS, IGNORED_USERS, AFK_MODE, AFK_REASON, WORKING_HOURS_ONLY, START_HOUR, END_HOUR, WELCOME_MSG_ENABLED, KNOWN_CONTACTS, USER_LAST_MSG_TIME
    try:
        user_id = event.sender_id
        if not user_id or user_id in IGNORED_USERS:
            return

        # 1. Anti-Spam Cooldown
        current_time = time.time()
        if user_id in USER_LAST_MSG_TIME and (current_time - USER_LAST_MSG_TIME[user_id] < 10):
            return
        USER_LAST_MSG_TIME[user_id] = current_time

        # 2. Quiet Hours Check
        if WORKING_HOURS_ONLY:
            tz = pytz.timezone('Asia/Colombo')
            current_hour = datetime.now(tz).hour
            if START_HOUR <= current_hour < END_HOUR:
                return

        # 3. AFK Check
        if AFK_MODE:
            await event.reply(f"🤖 {AFK_REASON}")
            return

        # 4. Welcome Message Check
        if WELCOME_MSG_ENABLED and user_id not in KNOWN_CONTACTS:
            try:
                full_user = await client(GetFullUserRequest(user_id))
                user_obj = full_user.users[0]
                if not user_obj.contact and not user_obj.bot:
                    await event.reply("💌 Hey! 💖 Thanks for your message. I'll reply soon. 😊")
                    KNOWN_CONTACTS.add(user_id)
                    await save_bot_data()
            except Exception as ex:
                print(f"Welcome Fetch Error: {ex}")

        incoming_raw = event.raw_text.strip().lower() if event.raw_text else ""
        if not incoming_raw:
            return

        replied = False

        # 5. Media Auto-Reply Check
        if incoming_raw in MEDIA_RESPONSES:
            msg_id = MEDIA_RESPONSES[incoming_raw]
            try:
                saved_msg = await client.get_messages(STORAGE_CHANNEL, ids=msg_id)
                if saved_msg:
                    await event.reply(saved_msg)
                    replied = True
            except Exception:
                pass

        # 6. Custom Text Reply Check
        if not replied:
            words_in_msg = re.findall(r'\b\w+\b', incoming_raw)
            for word, reply in RESPONSES.items():
                target_word = word.strip().lower()
                if target_word and (target_word == incoming_raw or target_word in words_in_msg):
                    await event.reply(reply)
                    replied = True
                    break

        # 7. Gemini AI / Default Reply
        if not replied and user_id not in REPLIED_USERS:
            if AI_REPLY_ENABLED and ai_model:
                try:
                    prompt = f"You are a friendly personal assistant for an A/L Combined Maths student. Briefly answer this message in Singlish/Sinhala in 1-2 friendly sentences: '{incoming_raw}'"
                    response = ai_model.generate_content(prompt)
                    if response.text:
                        await event.reply(f"{response.text.strip()}\n\n_(🤖 Auto-Reply)_")
                        replied = True
                except Exception as ai_err:
                    print(f"Gemini AI Error: {ai_err}")

            if not replied:
                await event.reply("මං පොඩි වැඩක ඉන්නේ. 💻 මේක Auto Reply එකක්, ආපු ගමන් මැසේජ් එකක් දාන්නම්..! ✨")
            
            REPLIED_USERS.add(user_id)

    except Exception as e:
        print(f"Reply Error: {e}")

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
        try:
            await client.send_message(STORAGE_CHANNEL, "🚀 **Dashboard Upgraded with AI & Anti-Spam Engine!**")
        except Exception:
            pass
        await client.run_until_disconnected()

    client.loop.run_until_complete(start_bot())
