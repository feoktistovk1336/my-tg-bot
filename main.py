import os
import asyncio
import random
import aiohttp
import aiosqlite
import logging

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
logger = logging.getLogger("SAAS")

# =========================
# BOT
# =========================

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)

dp = Dispatcher()

# =========================
# LIMITS (SaaS CORE)
# =========================

FREE_LIMIT = 5  # бесплатных генераций

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

AI_SYSTEM = """
Ты premium AI creator.
Стиль: cinematic, viral, emotional, Gen Z.
"""

# =========================
# DB INIT
# =========================

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            usage INTEGER DEFAULT 0,
            plan TEXT DEFAULT 'free'
        )
        """)
        await db.commit()

async def get_user(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT usage, plan FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        if not row:
            await db.execute("INSERT INTO users (user_id, usage, plan) VALUES (?,0,'free')", (user_id,))
            await db.commit()
            return 0, "free"
        return row

async def increase_usage(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET usage = usage + 1 WHERE user_id=?", (user_id,))
        await db.commit()

# =========================
# KEYBOARD
# =========================

def menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🤖 AI пост")],
            [KeyboardButton(text="🎬 AI reels")],
            [KeyboardButton(text="📸 AI карусель")],
            [KeyboardButton(text="💳 Мой тариф")],
        ],
        resize_keyboard=True
    )

# =========================
# AI API
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
    return await ask_groq(f"Вирусный пост: {topic}")

async def ai_reels(topic):
    return await ask_groq(f"Reels сценарий HOOK→PAYOFF: {topic}")

async def ai_carousel(topic):
    return await ask_groq(f"Instagram carousel 6 slides: {topic}")

# =========================
# SAAS CHECK
# =========================

async def check_limit(user_id: int):
    usage, plan = await get_user(user_id)

    if plan == "pro":
        return True, usage, plan

    if usage >= FREE_LIMIT:
        return False, usage, plan

    return True, usage, plan

# =========================
# HANDLER WRAPPER
# =========================

async def handle_ai(message: Message, generator):
    user_id = message.from_user.id

    ok, usage, plan = await check_limit(user_id)

    if not ok:
        await message.answer(
            "❌ Лимит бесплатного тарифа исчерпан.\n"
            "💳 Обнови тариф для продолжения."
        )
        return

    topic = random.choice(TOPICS)

    await message.answer("⏳ Генерация AI контента...")

    text = await generator(topic)

    await increase_usage(user_id)

    await message.answer(
        f"🔥 <b>AI CONTENT</b>\n\n{text}\n\n"
        f"📊 Usage: {usage + 1}/{FREE_LIMIT if plan=='free' else '∞'}"
    )

# =========================
# COMMANDS
# =========================

@dp.message(Command("start"))
async def start(message: Message):
    await message.answer(
        "🚀 AI SaaS Bot V4 запущен",
        reply_markup=menu()
    )

# =========================
# AI BUTTONS
# =========================

@dp.message(F.text == "🤖 AI пост")
async def post_handler(message: Message):
    await handle_ai(message, ai_post)

@dp.message(F.text == "🎬 AI reels")
async def reels_handler(message: Message):
    await handle_ai(message, ai_reels)

@dp.message(F.text == "📸 AI карусель")
async def carousel_handler(message: Message):
    await handle_ai(message, ai_carousel)

# =========================
# PLAN INFO
# =========================

@dp.message(F.text == "💳 Мой тариф")
async def plan(message: Message):
    usage, plan = await get_user(message.from_user.id)

    await message.answer(
        f"💳 Тариф: <b>{plan}</b>\n"
        f"📊 Использовано: <b>{usage}/{FREE_LIMIT}</b>\n\n"
        f"{'🔥 PRO = без лимитов' if plan=='free' else '🚀 активен PRO'}"
    )

# =========================
# MAIN
# =========================

async def main():
    await init_db()
    logger.info("V4 SaaS Bot started")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
