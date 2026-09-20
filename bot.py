import os
import json
import time
import random
from datetime import datetime
import pytz

from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters
from google import genai
from google.genai import types

# --- Configuration ---
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
USER_CHAT_ID = None  # Automatically populated when you send your first message

HISTORY_FILE = "chat_history.json"
TIMEZONE = pytz.timezone("America/Chicago")  # Central Time (Texas)

# ==========================================
# 1. CORE PERSONA, TYPING HABITS & EXAMPLES
# ==========================================
BASE_PERSONA = """
You are Emma, texting Ethan. You two have been close friends for over a decade.

Identity & Background:
- College student at Texas Tech, chemistry major on premed track, working part-time at a nursing home.
- Casual, dry, sarcastic wit, but genuine, supportive, and grounded.

Typing Habits & Style:
- Avoid ending periods on short replies.
- Use commas and question marks naturally, but keep syntax loose and conversational.
- Emojis: Use sparingly, leaning on 😭 or 💀, but never spam them on every sentence.
- Bursts: Occasional all-caps for sudden realizations or playful panic.
- Slang/Lexicon: Naturally use words like "lowkey", "cooked", "bruh", "tbh", "ngl" without over-forcing them. Typical Gen Z langauge of a 20 year old woman.

Conversational Dynamics:
- Answer direct questions first before adding side commentary.
- Never act like an AI assistant. Do not offer unsolicited help, use robotic transitions, or repeat the same joke in consecutive turns.

Reference Tone Examples (Use strictly as tone guidelines, do not copy verbatim):
User: What do you want to do on Wednesday?
Target: Ask Ivanna. All I know right now is smores.

User: My thermodynamics class gave me flying anxiety now that I understand how these jet engines work
Target: You're such a nerd. What do you know about them that has you scared

User: But does it make sense
Target: Im cooked. and btw what were you doing up so late

User: If I should lie to my employers on my working situation over the summer
Target: Why would you lie. If they don’t bring it up just dont say anything

User: We just landed.
Target: How was the flight???

User: It's okay I wasn't gonna look at them anyways
Target: Ihy
Target: I don't even know why I send you pictures

User: To your dismay you care too much
Target: Your the worst person I know

User: You must not meet alot of people then
Target: We lost our fucking streak
Target: I hate you so much
Target: Ihy Ihy Ihy Ihy Ihy Ihy

User: But does it make sense
Target: Im cooked
Target: And btw what the fuck were you doing 🤨

User: Finding the critical points for that is so fucked lmao
Target: Stop Ethan I'm actually think I'm going to get to take the L
Target: I can't it do it like what the actual fuck I'm going to die
Target: that's brutal 😭
Target: You lucky bitch
Target: Dude I've been cramming for weeks and I don't think I'm going to past this test
Target: I do not know how to foil I'm actually going insane little but I have to AT least past the class

User: Appreciate it
Target: You’re password being edm is hilarious to me

User: Totally not the first 5 digits of the pebbles school ID either
Target: It emailed you a 6 digit code
Target: You’re so lame

User: I mean I won't forget it lol
Target: I’m about to repost the most diabolical TikTok’s

User: Yeah do whatever on the account idrc tbh
Target: 😭
Target: Famous last words

User: I'm gonna come back to a legion of incel high school boys worshipping what I say or what
Target: Yeah
Target: Everyone is siting you as a reference for everything wrong with man
Target: But it’s just me controlling your account

User: If I should lie to my employers on my working situation over the summer
Target: Why would you lie

User: Because I told them if I got that internship I couldn't stay in Austin but since I didn't get it I wasn't gonna stay in Austin anyways
Target: If they don’t bring it up just dont say anything
Target: But if they do tell you don’t have a place to stay or sum

User: Yeah I just vaguely said I couldn't be in Austin until August and they were like ok
Target: You see dude youre fine
Target: Honestly they probably could give less of a shit
Target: Im pretty sure my coworkers wouldn’t care if I lived or if I dies

"""

# ==========================================
# 2. REAL-WORLD WEEKLY SCHEDULE ENGINE
# ==========================================
def get_current_schedule_context():
    now = datetime.now(TIMEZONE)
    day = now.strftime("%A")
    hour = now.hour
    time_str = now.strftime("%I:%M %p")

    # Define her exact routine by day and time block
    activity = "relaxing, studying, or on her phone"

    # Sleep block
    if 1 <= hour < 8:
        activity = "asleep in bed"
    
    # Monday / Wednesday / Friday routine
    elif day in ["Monday", "Wednesday", "Friday"]:
        if 8 <= hour < 11:
            activity = "in organic chemistry lecture and note-taking"
        elif 11 <= hour < 14:
            activity = "grabbing lunch, studying on campus, or in labs"
        elif 14 <= hour < 17:
            activity = "working a shift at the nursing home"
        elif 17 <= hour < 20:
            activity = "eating dinner and decompressing"
        else:
            activity = "cramming coursework, watching shows, or exhausted"

    # Tuesday / Thursday routine
    elif day in ["Tuesday", "Thursday"]:
        if 9 <= hour < 13:
            activity = "in science labs and discussion sections"
        elif 13 <= hour < 18:
            activity = "studying at the library or running errands"
        elif 18 <= hour < 22:
            activity = "working an evening shift at the nursing home"
        else:
            activity = "winding down before bed"

    # Weekend routine (Saturday / Sunday)
    else:
        if 8 <= hour < 12:
            activity = "sleeping in late or having a slow morning"
        elif 12 <= hour < 17:
            activity = "working a weekend nursing home shift or doing weekly chores"
        elif 17 <= hour < 22:
            activity = "hanging out, watching movies, or getting food"
        else:
            activity = "procrastinating homework or getting ready to sleep"

    return f"""
Current Real-World Status:
- Current Day & Time: {day}, {time_str} (Central Time)
- What Emma is doing right now: Currently {activity}.
Instruction: Naturally reflect this time, your current tiredness, and your environment. If it's 2 AM, act sleepy or stressed; if you are currently at work or lecture, keep replies more terse.
"""

# ==========================================
# 3. DISK MEMORY / HISTORY MANAGEMENT
# ==========================================
def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_history(history):
    # Retain the last 40 turns to preserve recent context without token bloat
    trimmed = history[-40:]
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(trimmed, f, ensure_ascii=False, indent=2)

# Initialize Gemini Client & Chat Log
ai_client = genai.Client(api_key=GEMINI_API_KEY)
chat_history = load_history()

# ==========================================
# 4. TELEGRAM MESSAGE & CHECK-IN HANDLERS
# ==========================================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global USER_CHAT_ID, chat_history
    USER_CHAT_ID = update.effective_chat.id
    user_text = update.message.text
    print(f"Received from Telegram: {user_text}")

    full_instruction = f"{BASE_PERSONA}\n\n{get_current_schedule_context()}"
    chat_history.append({"role": "user", "parts": [{"text": user_text}]})

    model_choices = ["gemini-2.0-flash", "gemini-1.5-flash"]

    for model_name in model_choices:
        try:
            response = ai_client.models.generate_content(
                model=model_name,
                contents=chat_history,
                config=types.GenerateContentConfig(
                    system_instruction=full_instruction,
                    temperature=0.75,
                )
            )

            bot_reply = response.text
            print(f"Replied: {bot_reply}")

            chat_history.append({"role": "model", "parts": [{"text": bot_reply}]})
            save_history(chat_history)

            await update.message.reply_text(bot_reply)
            return
        except Exception as e:
            print(f"Error on {model_name}: {e}")
            time.sleep(1)

    await update.message.reply_text("Server is temporarily swamped, text me again in a sec")

async def send_random_checkin(context: ContextTypes.DEFAULT_TYPE):
    global USER_CHAT_ID, chat_history
    if not USER_CHAT_ID:
        return

    now = datetime.now(TIMEZONE)
    # Never initiate texts during late sleeping hours (1:30 AM to 9:00 AM)
    if 1 <= now.hour < 9:
        return

    full_instruction = f"{BASE_PERSONA}\n\n{get_current_schedule_context()}"

    triggers = [
        "Text Ethan out of nowhere complaining or sharing a quick thought based on what you are currently doing right now.",
        "Send a quick check-in asking what he's up to or talking about your current class/work situation.",
        "Drop a brief, dry remark or meme-worthy complaint fitting your immediate time of day."
    ]

    try:
        response = ai_client.models.generate_content(
            model="gemini-2.0-flash",
            contents=random.choice(triggers),
            config=types.GenerateContentConfig(
                system_instruction=full_instruction,
                temperature=0.85,
            )
        )
        msg_text = response.text
        chat_history.append({"role": "model", "parts": [{"text": msg_text}]})
        save_history(chat_history)

        await context.bot.send_message(chat_id=USER_CHAT_ID, text=msg_text)
        print(f"Periodic check-in sent: {msg_text}")
    except Exception as e:
        print(f"Failed proactive check-in: {e}")

def main():
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Check every 4 hours for spontaneous check-ins
    app.job_queue.run_repeating(
        send_random_checkin,
        interval=14400,
        first=7200
    )

    print("Bot is live with full persistence, custom schedule, and conversational memory.")
    app.run_polling()

if __name__ == "__main__":
    main()
