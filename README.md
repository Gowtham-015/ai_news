# AI News Automation Agent — Phase 1 & Phase 2

⚠️ **SECURITY WARNING**
Your `TELEGRAM_BOT_TOKEN` is a secret password for your bot. Anyone who has
it can control your bot completely.
- **Never** share it in chat, screenshots, forums, or GitHub.
- **Never** remove it from the `.env` file and paste it into `bot.py` or
  `config.py`.
- The `.env` file is already excluded from Git via `.gitignore`, so it
  won't accidentally get uploaded if you push this project to GitHub.
- If you ever think your token was leaked, go to @BotFather in Telegram
  and generate a new one (`/mybots` → your bot → API Token → Revoke
  current token).

## What Phase 1 does

This is the very first building block of the AI News Automation Agent.
Right now, the project does exactly one thing:

```
Python application → Telegram Bot API → Telegram Bot → Your Telegram Channel → Test message appears
```

It does **not** collect news, use AI, run on a schedule, or use a
database yet — that comes in later phases. Phase 1 only proves that your
Python code can successfully talk to Telegram and post into your channel.

## Project structure

```
AI_News_Agent/
│
├── bot.py             # Phase 1: connects to Telegram and sends the test message
├── config.py           # Loads and validates secrets from .env (used by both phases)
├── publisher.py         # Phase 2: reusable function that sends any text to your channel
├── scheduler.py          # Phase 2: the program you run — checks posts.json and auto-publishes
├── posts.json             # Phase 2: your list of scheduled posts
├── scheduler.log            # Phase 2: created automatically once you run scheduler.py
├── requirements.txt          # List of Python packages this project needs
├── .env                        # Your secret token and channel ID (never share this file)
├── .gitignore                   # Tells Git to ignore .env and other junk files
└── README.md                     # This file
```

### What each file is for

- **`bot.py`** — Phase 1 script. Sends one hard-coded test message. You
  don't need to run this anymore day-to-day, but it's still useful for
  quickly checking your Telegram connection works.
- **`config.py`** — Loads and validates `TELEGRAM_BOT_TOKEN` and
  `TELEGRAM_CHANNEL_ID` from `.env`. Used by both `bot.py` and
  `publisher.py` — nothing is duplicated between phases.
- **`publisher.py`** *(new in Phase 2)* — A small, reusable function,
  `publish_text(text)`, that sends any text to your Telegram channel and
  returns `True`/`False`. It doesn't know anything about schedules or
  posts.json — its only job is "given some text, send it, tell me if it
  worked."
- **`scheduler.py`** *(new in Phase 2 — this is the program you run)* —
  Runs continuously in the background. Every 30 seconds it checks
  `posts.json` for posts whose scheduled time has arrived, and publishes
  them via `publisher.py`.
- **`posts.json`** *(new in Phase 2)* — Your list of posts, each with a
  category, title, content, and scheduled time. This is currently edited
  by hand; in a later phase this could be filled automatically.
- **`scheduler.log`** *(new in Phase 2)* — A plain text log file created
  automatically the first time you run `scheduler.py`. Contains a
  timestamped history of what the scheduler did (checks, publishes,
  errors) — useful for reviewing what happened while you weren't
  watching the terminal.
- **`requirements.txt`** — A plain text list of the external packages
  needed to run this project. `pip install -r requirements.txt` reads
  this file and installs everything listed.
- **`.env`** — Holds your actual secret values. This file is never
  uploaded to GitHub (see `.gitignore`) and is never read by anything
  except `config.py`.
- **`.gitignore`** — Tells Git which files/folders to never track,
  most importantly `.env` (your secrets) and `venv/` (your virtual
  environment, which is large and machine-specific).

---

## Step-by-step setup (Windows)

### STEP 1 — Open the project folder

Open **File Explorer**, navigate to the `AI_News_Agent` folder, then open
a terminal there. The easiest way: inside the folder, click the address
bar, type `cmd`, and press Enter. This opens Command Prompt already
pointed at the right folder.

### STEP 2 — Create a virtual environment

A virtual environment is an isolated, self-contained copy of Python just
for this project, so the packages you install here don't affect any
other Python project on your computer.

```
python -m venv venv
```

This creates a new folder called `venv/` inside your project.

### STEP 3 — Activate the virtual environment

```
venv\Scripts\activate
```

If it worked, your terminal prompt will now start with `(venv)`. You
need to do this every time you open a new terminal to work on this
project — it tells Windows "use the Python packages inside `venv/`, not
the system-wide ones."

> If you get a "running scripts is disabled" error, open PowerShell as
> Administrator and run:
> `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`
> then try activating again.

### STEP 4 — Install dependencies

```
pip install -r requirements.txt
```

This installs `python-telegram-bot` (talks to the Telegram API),
`python-dotenv` (loads your `.env` file), `APScheduler` (runs the
Phase 2 scheduling loop), and `tzdata` (gives Windows the timezone
data needed for accurate Asia/Kolkata scheduling). You'll see
download/install progress in the terminal.

### STEP 5 — Create your `.env` file

A `.env` file is already included in this project as a template. If for
any reason it's missing, create a new plain text file named exactly
`.env` (no `.txt` at the end) in the project folder with this content:

```
TELEGRAM_BOT_TOKEN=YOUR_BOT_TOKEN_HERE
TELEGRAM_CHANNEL_ID=YOUR_CHANNEL_ID_HERE
```

### STEP 6 — Put your Telegram bot token into `.env`

If you don't have a bot yet:
1. Open Telegram and search for **@BotFather**.
2. Send `/newbot` and follow the prompts (choose a name and a username
   ending in `bot`).
3. BotFather will reply with a token that looks like:
   `123456789:AAExampleTokenTextGoesHere`
4. Copy that token and paste it into `.env`, replacing
   `YOUR_BOT_TOKEN_HERE`, so the line looks like:
   `TELEGRAM_BOT_TOKEN=123456789:AAExampleTokenTextGoesHere`

If you already have a bot, get its token the same way via
`/mybots` → select your bot → **API Token**.

### STEP 7 — Find your Telegram Channel ID

1. Create a Telegram **channel** if you don't have one yet (Telegram app
   → New Message → New Channel).
2. Add your bot to the channel as an **Administrator**:
   - Open the channel → tap the channel name → **Administrators** →
     **Add Admin** → search for your bot by its username → give it
     permission to **Post Messages**.
3. Get the channel's numeric ID. The simplest way:
   - Post any message in your channel.
   - Forward that message to the Telegram bot **@userinfobot** (or
     **@JsonDumpBot**), and it will show you the channel's ID.
   - It will look like a negative number, e.g. `-1001234567890`.
   - Alternative method: if your channel has a public username (e.g.
     `@my_news_channel`), you can use that directly as the channel ID
     instead of the numeric ID: `TELEGRAM_CHANNEL_ID=@my_news_channel`.
4. Paste the ID into `.env`, replacing `YOUR_CHANNEL_ID_HERE`:
   `TELEGRAM_CHANNEL_ID=-1001234567890`

### STEP 8 — Run the program

Make sure your virtual environment is still active (prompt starts with
`(venv)`), then run:

```
python bot.py
```

### STEP 9 — What successful output looks like

You should see something like this in the terminal:

```
========================================
 AI News Automation Agent - PHASE 1
 Testing Telegram connection...
========================================

[config] Configuration loaded successfully. (Token hidden for security)
[bot] Connected to Telegram as: @your_bot_username

========================================
 SUCCESS: Test message sent to your channel!
========================================
Go check your Telegram channel now — the message
should already be visible there.

[bot] Done. Exiting cleanly.
```

Notice that your actual token is never printed — only the bot's public
username is shown, as confirmation that the connection worked.

### STEP 10 — What to check in Telegram

Open your Telegram channel. You should see a new post from your bot
that reads:

```
🤖 AI News Agent is connected!
This is my first automated Telegram post.

📰 News
💻 Technology
🏏 Sports
🎬 Entertainment

Automation system: ONLINE ✅
```

If you see this message in your channel, Phase 1 is complete and
working correctly.

---

## Troubleshooting guide

| Error in terminal | What it means | How to fix it |
|---|---|---|
| **Invalid Token / Unauthorized (401)** | Your bot token is wrong, mistyped, or was revoked | Get a fresh token from @BotFather (`/mybots` → your bot → API Token) and paste it exactly into `.env` with no extra spaces or quotes |
| **Forbidden (403)** | Your bot doesn't have permission to post in the channel | Add the bot as an **Administrator** of the channel with "Post Messages" permission enabled |
| **Bad Request / Chat not found** | The `TELEGRAM_CHANNEL_ID` is wrong or the bot isn't in the channel yet | Double-check the ID format (`-100...` for private numeric IDs, or `@channelname` for public channels); make sure the bot was added to the channel |
| **Network error / Timed out** | Your computer couldn't reach Telegram's servers | Check your internet connection, check if a firewall/VPN/antivirus is blocking the app, then try again |
| **CONFIGURATION ERROR (missing values)** | `.env` is missing or incomplete | Make sure `.env` exists in the project folder and both `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHANNEL_ID` are filled in |

If none of these match your error, read the full error message printed
in the terminal — `bot.py` is written to explain what went wrong in
plain English above the technical details.

---

---

# Phase 2 — Automatic Telegram Posting & Scheduling

## What Phase 2 adds

Phase 1 could only send one hard-coded message when you ran it by hand.
Phase 2 adds a proper publishing pipeline:

```
posts.json (scheduled content)
        ↓
scheduler.py (checks every 30 seconds: "is anything due?")
        ↓
publisher.py (sends the text to Telegram)
        ↓
Telegram Bot
        ↓
Your Telegram Channel
```

You write posts into `posts.json` ahead of time (with a category, title,
content, and scheduled time), start `scheduler.py` once, and it keeps
running in the background, automatically publishing each post exactly
when its scheduled time arrives — no manual command per post.

Still **not** included yet (this is intentional, per the phased plan):
AI-generated content, news scraping/RSS, Instagram, a database, or a
website. `posts.json` is your database for now, and you fill it in by
hand.

## How scheduling works (not a plain `while True: sleep()` loop)

`scheduler.py` uses **APScheduler**, a well-established Python
scheduling library, instead of a hand-rolled infinite loop. APScheduler
manages the timing precisely, handles the waiting between checks, and
lets you stop the program safely with `Ctrl+C`. Every 30 seconds, it
calls a function that reads `posts.json`, checks which posts are due,
and publishes them.

## How timezone handling works

You're in India, so **all** `scheduled_time` values in `posts.json` are
interpreted in the **Asia/Kolkata** timezone — explicitly, using
Python's `zoneinfo` module — regardless of what timezone your computer
itself is set to. This means the schedule behaves consistently even if
you later move this project to a cloud server set to UTC.

Windows doesn't include the official timezone database that `zoneinfo`
needs to know what "Asia/Kolkata" means, so this project depends on the
small `tzdata` package (already in `requirements.txt`) to supply it.

## `posts.json` — your scheduled posts

Each post is a JSON object with these fields:

| Field | Meaning |
|---|---|
| `id` | A unique number identifying the post |
| `category` | `NEWS`, `TECHNOLOGY`, `SPORTS`, or `ENTERTAINMENT` (controls the emoji used) |
| `title` | Short headline shown at the top of the message |
| `content` | The body text of the post |
| `scheduled_time` | When to publish, in the exact format `YYYY-MM-DD HH:MM:SS`, interpreted as Asia/Kolkata time |
| `status` | `"scheduled"` (not sent yet) or `"published"` (already sent) — you should always create new posts with `"scheduled"` |
| `published_time` | Filled in automatically once the post is sent; leave as `null` when creating a post |

The project comes with 3 example posts already in `posts.json` — one
each for NEWS, TECHNOLOGY, and SPORTS — so you can see the format and
test right away.

### How to schedule a test post 1–2 minutes in the future

This is the fastest way to see the scheduler actually work:

1. Open `posts.json` in a text editor (Notepad is fine).
2. Check the current time on your computer (Asia/Kolkata / IST).
3. Pick a time about 2 minutes from now and write it in the exact
   format `YYYY-MM-DD HH:MM:SS`. For example, if it's currently
   `2026-08-18 14:30:00`, use `2026-08-18 14:32:00`.
4. Edit one of the example posts' `scheduled_time` field to that value
   (make sure its `status` is `"scheduled"`).
5. Save the file, then start the scheduler (see below) and watch the
   terminal — within about 30 seconds of your chosen time, you should
   see it get published.

## Installation (if you haven't already installed Phase 1's requirements)

```
pip install -r requirements.txt
```

This now also installs `APScheduler` and `tzdata` in addition to the
Phase 1 packages. If you already set up your virtual environment for
Phase 1, just re-run this command inside it to pick up the two new
packages.

## Running the scheduler

Make sure your virtual environment is active (prompt starts with
`(venv)`), then run:

```
python scheduler.py
```

This will keep running continuously — that's expected. It will check
`posts.json` every 30 seconds and publish anything that's due. Leave
this terminal window open for as long as you want automatic posting to
continue.

### Expected terminal output

```
2026-08-18 14:00:00 - INFO - Scheduler started
2026-08-18 14:00:00 - INFO - Checking posts.json every 30 seconds (timezone: Asia/Kolkata)
2026-08-18 14:00:01 - INFO - Publishing post 1
2026-08-18 14:00:02 - INFO - Post 1 published successfully
```

If a post fails to publish (e.g. a temporary network hiccup), you'll
see something like:

```
2026-08-18 14:05:01 - INFO - Publishing post 2
2026-08-18 14:05:02 - ERROR - Failed to publish post 2
```

That post stays marked `"scheduled"` and will automatically be retried
on the next check (about 30 seconds later) — you don't need to do
anything.

Everything printed to the terminal is also saved to `scheduler.log` in
your project folder, so you can review what happened even after you've
closed the terminal. The bot token is never printed or logged, in the
terminal or in the log file.

### What to check in Telegram

Each published post appears in your channel formatted like this
(example for a NEWS post):

```
📰 Morning News

This is a test news update from Phase 2 of the AI News Automation Agent.
```

The emoji changes based on category: 📰 News, 💻 Technology, 🏏 Sports,
🎬 Entertainment.

### How to stop the scheduler safely

Click into the terminal window running `scheduler.py` and press
`Ctrl+C`. You'll see:

```
2026-08-18 14:10:00 - INFO - Scheduler stopped by user
```

This is a clean shutdown — it won't corrupt `posts.json` or leave
anything half-published. It's safe to stop and restart the scheduler
at any time; already-published posts won't be sent again, since their
`status` is `"published"`.

## Reliability — what happens when things go wrong

- **Malformed `posts.json`** (e.g. you accidentally broke the JSON
  formatting while editing) — the scheduler logs a clear error and
  simply skips that check cycle, trying again on the next one. It does
  not crash.
- **Missing `.env` values** — `publisher.py` checks configuration
  before every publish attempt and logs a clear error if something's
  missing, rather than crashing the whole scheduler.
- **Invalid `scheduled_time` format** on one post — that specific post
  is skipped with a logged error; every other post is still checked
  and published normally.
- **A single Telegram API failure** (network blip, rate limit, etc.) —
  only that post is affected. It stays `"scheduled"` and is retried
  automatically on the next check; all other posts continue processing
  normally.
- **Duplicate publishing** is avoided because the scheduler only ever
  looks at posts with `status: "scheduled"` — once a post is marked
  `"published"`, it's permanently skipped on future checks.

## Troubleshooting guide (Phase 2 additions)

| Symptom | What it means | How to fix it |
|---|---|---|
| `posts.json not found` | The file is missing from the project folder | Make sure `posts.json` exists in the same folder as `scheduler.py` |
| `posts.json contains invalid JSON` | You edited the file and broke its formatting (e.g. a missing comma or bracket) | Open it in a text editor and check for typos; a tool like jsonlint.com can help spot the exact issue |
| Post never publishes even though the time passed | `scheduled_time` format is wrong, or `status` isn't `"scheduled"` | Check the format is exactly `YYYY-MM-DD HH:MM:SS` and `status` is `"scheduled"`; check `scheduler.log` for a specific error |
| `Failed to publish post N` repeating every cycle | Same Telegram errors as Phase 1 (bad token, bot not admin, wrong channel ID, network issue) | See the Phase 1 troubleshooting table above — the same fixes apply here |
| Times seem off by a few hours | Your `scheduled_time` wasn't written in Asia/Kolkata time | Remember: all times in `posts.json` are always treated as IST, regardless of your PC's timezone setting |

---

## How Phase 2 connects to Phase 3 (preview only — not built yet)

Phase 2 built a reliable "publish this text, on this schedule" system —
`posts.json` is currently your source of truth, filled in by hand.

- **Phase 3** will likely introduce AI content generation, replacing the
  manual step of writing `title`/`content` yourself. The AI would
  generate that text and write new entries into `posts.json` (or a
  successor to it), which `scheduler.py` would then pick up and publish
  exactly as it does now — no changes needed to `scheduler.py` or
  `publisher.py` themselves.
- Later phases will likely add real news sources (feeding the AI
  something to summarize) and possibly a database to replace
  `posts.json` once the volume of posts grows.
- `publisher.py`'s `publish_text(text)` function is intentionally
  generic — it doesn't care whether the text came from you typing it
  into `posts.json` by hand or from an AI model. That's exactly what
  will let Phase 3 plug in AI-generated content without needing to
  touch the Telegram-publishing logic at all.

No code for Phase 3 has been written yet, as requested — Phase 2 stands
alone and fully working on its own.
