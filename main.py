import os
import asyncio
import random
import logging
import aiohttp
import sqlite3

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import Command
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

# =========================
# CONFIG
# =========================

BOT_TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

DB_PATH = "saas.db"

# =========================
# LOGGING
# =========================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("SAAS_V4")

# =========================
# BOT INIT
# =========================

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)

dp = Dispatcher()

# =========================
# TOPICS
# =========================

TOPICS = [
    "AI меняет мир",
    "TikTok алгоритмы",
    "Instagram рост",
    "Вирусный контент",
    "AI видео",
    "Digital creator",
]

# =========================
# AI STYLE
# =========================

AI_SYSTEM = """
Ты premium AI creator уровня топового TikTok/Instagram блогера.

Стиль:
- cinematic
- viral hooks
- эмоциональный сторителлинг
- Gen Z tone

Всегда:
- strong HOOK в начале
- короткие абзацы
- emoji уместно
- CTA в конце
"""

# =========================
# DB (FIXED SQLITE)
# =========================

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        usage INTEGER DEFAULT 0,
        plan TEXT DEFAULT 'free'
    )
    """)

    conn.commit()
    conn.close()


def get_user(user_id: int):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("SELECT usage, plan FROM users WHERE user_id=?", (user_id,))
    row = cur.fetchone()

    if not row:
        cur.execute(
            "INSERT INTO users (user_id, usage, plan) VALUES (?,0,'free')",
            (user_id,)
        )
        conn.commit()
        conn.close()
        return 0, "free"

    conn.close()
    return row


def increase_usage(user_id: int):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute(
        "UPDATE users SET usage = usage + 1 WHERE user_id=?",
        (user_id,)
    )

    conn.commit()
    conn.close()

# =========================
# LIMITS
# =========================

FREE_LIMIT = 5

def check_limit(user_id: int):
    usage, plan = get_user(user_id)

    if plan == "pro":
        return True, usage, plan

    if usage >= FREE_LIMIT:
        return False, usage, plan

    return True, usage, plan

# =========================
# KEYBOARD
# =========================

def menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🤖 AI пост")],
            [KeyboardButton(text="🎬 AI reels")],
            [KeyboardButton(text="📸 AI карусель")],
            [KeyboardButton(text="💳 Тариф")],
        ],
        resize_keyboard=True
    )

# =========================
# GROQ AI
# =========================

async def ask_groq(prompt: str):
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {"role": "system", "content": AI_SYSTEM},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.9
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers=headers,
            json=payload
        ) as r:
            data = await r.json()
            return data["choices"][0]["message"]["content"]

# =========================
# AI FUNCTIONS
# =========================

async def ai_post(topic):
    return await ask_groq(f"Вирусный пост (80-120 слов): {topic}")

async def ai_reels(topic):
    return await ask_groq(f"Reels сценарий HOOK → PAYOFF: {topic}")

async def ai_carousel(topic):
    return await ask_groq(f"Instagram carousel 6 slides: {topic}")

# =========================
# CORE HANDLER
# =========================

async def run_ai(message: Message, func):
    user_id = message.from_user.id

    ok, usage, plan = check_limit(user_id)

    if not ok:
        await message.answer(
            "❌ Лимит бесплатного тарифа исчерпан.\n💳 Перейдите на PRO."
        )
        return

    topic = random.choice(TOPICS)

    await message.answer("⏳ Генерация AI контента...")

    result = await func(topic)

    increase_usage(user_id)

    await message.answer(
        f"🔥 <b>AI CONTENT</b>\n\n{result}\n\n"
        f"📊 Использовано: {usage + 1}/{FREE_LIMIT if plan=='free' else '∞'}"
    )

# =========================
# COMMANDS
# =========================

@dp.message(Command("start"))
async def start(message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    await message.answer(
        "🚀 V4 SaaS AI Bot запущен",
        reply_markup=menu()
    )

# =========================
# BUTTONS
# =========================

@dp.message(F.text == "🤖 AI пост")
async def post_handler(message: Message):
    await run_ai(message, ai_post)

@dp.message(F.text == "🎬 AI reels")
async def reels_handler(message: Message):
    await run_ai(message, ai_reels)

@dp.message(F.text == "📸 AI карусель")
async def carousel_handler(message: Message):
    await run_ai(message, ai_carousel)

@dp.message(F.text == "💳 Тариф")
async def tariff(message: Message):
    usage, plan = get_user(message.from_user.id)

    await message.answer(
        f"💳 Тариф: <b>{plan}</b>\n"
        f"📊 Использование: <b>{usage}/{FREE_LIMIT}</b>\n\n"
        f"{'🔥 PRO без лимитов' if plan=='free' else '🚀 Активен PRO'}"
    )

# =========================
# MAIN
# =========================

async def main():
    init_db()
    logger.info("V4 SaaS Bot started")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
