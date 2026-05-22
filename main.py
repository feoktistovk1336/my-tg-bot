import os
import asyncio
import random
import logging
import aiohttp

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

# =========================
# CONFIG
# =========================

BOT_TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

CHANNEL_ID_RAW = os.getenv("CHANNEL_ID")  # @channel or -100123
ADMIN_ID = int(os.getenv("ADMIN_ID"))

CHANNEL_ID = (
    int(CHANNEL_ID_RAW) if CHANNEL_ID_RAW and CHANNEL_ID_RAW.lstrip("-").isdigit()
    else CHANNEL_ID_RAW
)

# =========================
# LOGGING
# =========================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("AI_BOT")

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
    "Будущее контента",
    "Вирусные нейросети",
    "AI video generation",
    "TikTok алгоритмы",
    "Instagram рост",
    "Digital creator 2026",
    "AI tools для заработка",
]

# =========================
# PREMIUM AI STYLE
# =========================

AI_SYSTEM = """
Ты premium AI creator уровня топового Instagram/TikTok блогера.

Стиль:
- cinematic
- дорогой визуальный стиль
- вирусные hooks
- эмоциональный сторителлинг
- Gen Z / TikTok tone

Правила:
- всегда начинай с сильного HOOK
- короткие абзацы
- emoji уместно
- финал = CTA
"""

# =========================
# KEYBOARD
# =========================

def main_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🤖 AI пост")],
            [KeyboardButton(text="🎬 AI reels")],
            [KeyboardButton(text="📸 AI карусель")],
        ],
        resize_keyboard=True
    )

# =========================
# GROQ API
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
        ) as resp:
            data = await resp.json()
            return data["choices"][0]["message"]["content"]

# =========================
# AI CONTENT
# =========================

async def ai_post(topic: str):
    prompt = f"""
Создай вирусный Telegram пост.

Тема: {topic}

80–120 слов.
"""
    return await ask_groq(prompt)


async def ai_reels(topic: str):
    prompt = f"""
Создай сценарий Instagram/TikTok Reels:

Тема: {topic}

Формат:
HOOK → PROBLEM → BUILD → PAYOFF → CTA
"""
    return await ask_groq(prompt)


async def ai_carousel(topic: str):
    prompt = f"""
Создай Instagram carousel (6 слайдов):

Тема: {topic}

Slide 1 = hook
Slide 2-5 = value
Slide 6 = CTA
"""
    return await ask_groq(prompt)

# =========================
# HANDLERS
# =========================

@dp.message(Command("start"))
async def start(message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    await message.answer(
        "🚀 AI Creator Bot запущен",
        reply_markup=main_menu()
    )

# =========================
# AI POST
# =========================

@dp.message(F.text == "🤖 AI пост")
async def handle_post(message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    await message.answer("⏳ Генерирую premium пост...")

    topic = random.choice(TOPICS)
    text = await ai_post(topic)

    await message.answer(f"🔥 <b>AI POST</b>\n\n{text}")

# =========================
# AI REELS
# =========================

@dp.message(F.text == "🎬 AI reels")
async def handle_reels(message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    await message.answer("🎬 Генерирую reels сценарий...")

    topic = random.choice(TOPICS)
    text = await ai_reels(topic)

    await message.answer(f"🎬 <b>REELS SCRIPT</b>\n\n{text}")

# =========================
# AI CAROUSEL
# =========================

@dp.message(F.text == "📸 AI карусель")
async def handle_carousel(message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    await message.answer("📸 Создаю карусель...")

    topic = random.choice(TOPICS)
    text = await ai_carousel(topic)

    await message.answer(f"📸 <b>CAROUSEL</b>\n\n{text}")

# =========================
# START BOT
# =========================

async def main():
    logger.info("Bot started")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
