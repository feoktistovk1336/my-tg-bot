import asyncio
import logging
import random
import aiohttp
from datetime import datetime

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BufferedInputFile

from apscheduler.schedulers.asyncio import AsyncIOScheduler


# =========================
# CONFIG
# =========================

BOT_TOKEN = "8925233625:AAE0lCKhErwAggy3HBal8VjO3TWXY5IFRzI"
CHANNEL_ID = "@primeonix26"
ADMIN_ID = "916037494"
GROQ_API_KEY = "Rnb8Lpn4"

POST_TIMES = [
    "12:00",
    "18:00"
]


# =========================
# LOGGING
# =========================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# =========================
# INIT
# =========================

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
scheduler = AsyncIOScheduler()


# =========================
# VIRAL TOPICS
# =========================

TOPICS = [
    "ChatGPT уже меняет мир",
    "AI превращает фото в мультфильм",
    "Топ AI tools 2026",
    "Новая нейросеть взорвала интернет",
    "AI теперь умеет создавать видео",
    "Будущее AI-контента",
    "Лучшие AI для фото",
    "Pixar-style через AI",
    "AI уже заменяет дизайнеров",
    "Будущее контента уже здесь",
]


# =========================
# GROQ REQUEST
# =========================

async def ask_groq(prompt: str):
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {
                "role": "system",
                "content": (
                    "Ты создаешь вирусный Telegram контент про AI. "
                    "Пиши как большой AI creator аккаунт. "
                    "Минимум воды. Короткие абзацы. Сильный hook."
                )
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        "temperature": 0.9,
    asyncio.run(main())
