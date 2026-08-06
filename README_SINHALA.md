# Userbot Sinhala Overview

මෙම userbot එක Telegram වලට වැඩ කරන sinhala-friendly assistant එකක්. Ownerට commands සහ public usersට auto-reply / AI උදව් දෙන පද්ධතියක්.

## Main features
- Owner commands: !status, !afk, !hours, !welcome, !ai, !add, !addmedia, !list, !block, !gcast, !reset
- Public commands: !help, !ping, !ask, !ytmp3, !exam
- AI auto-reply with Gemini
- AFK mode
- Working hours control
- Media auto-reply support
- Persistence to storage channel
- Flask health endpoint for hosting

## Public commands
- !help / !commands - commands list බලන්න
- !ping - bot alive ද බලන්න
- !ask <question> - AI/Study උදව් ගන්න
- !ytmp3 <youtube link> - YouTube audio download කරන්න
- !exam - A/L exam countdown බලන්න

## Owner commands
- !status - bot dashboard / settings බලන්න
- !afk / !afk off - AFK mode on/off
- !hours on/off - working hours toggle
- !hours range <start> <end> - working hour range set
- !welcome on/off - welcome message toggle
- !ai on/off - AI auto reply toggle
- !add word=reply - custom text reply එකතු කරන්න
- !del word - custom reply එක අයින් කරන්න
- !list - text replies list කරන්න
- !addmedia word - media reply එකතු කරන්න
- !delmedia word - media reply අයින් කරන්න
- !listmedia - media replies list කරන්න
- !block / !unblock - chat block/unblock
- !gcast <msg> - broadcast message
- !reset - reset history/contacts
- !todo <target> - study target එකතු කරන්න
- !done <number> - target complete කරන්න
- !cleartodo - targets clear කරන්න
