import asyncio
import logging
import random
import os
import aiohttp

from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message, BufferedInputFile

from apscheduler.schedulers.asyncio import AsyncIOScheduler


# ====================================
# CONFIG
# ====================================

BOT_TOKEN = os.getenv("8925233625:AAE0lCKhErwAggy3HBal8VjO3TWXY5IFRzI")
CHANNEL_ID = os.getenv("@primeonix26")
ADMIN_ID = int(os.getenv("916037494"))
import os

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
POST_TIMES = [
    "12:00",
    "18:00"
]


# ====================================
# LOGGING
# ====================================

logging.basicConfig(level=logging.INFO)

logger = logging.getLogger(__name__)


# ====================================
# INIT
# ====================================

bot = Bot(token=BOT_TOKEN)

dp = Dispatcher(storage=MemoryStorage())

scheduler = AsyncIOScheduler()


# ====================================
# TOPICS
# ====================================

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


# ====================================
# GROQ
# ====================================

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
                    "Пиши как premium AI creator аккаунт. "
                    "Делай сильный hook."
                )
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        "temperature": 0.9
    }

    async with aiohttp.ClientSession() as session:

        async with session.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers=headers,
            json=payload
        ) as response:

            data = await response.json()

            return data["choices"][0]["message"]["content"]


# ====================================
# IMAGE GENERATION
# ====================================

async def generate_image(prompt: str):

    try:

        url = (
            "https://image.pollinations.ai/prompt/"
            f"{prompt}?width=1024&height=1024&enhance=true"
        )

        async with aiohttp.ClientSession() as session:

            async with session.get(url) as response:

                if response.status == 200:

                    return await response.read()

    except Exception as e:

        logger.error(e)

    return None


# ====================================
# CREATE POST
# ====================================

async def create_post():

    topic = random.choice(TOPICS)

    prompt = f"""
    Напиши вирусный Telegram пост.

    Тема:
    {topic}

    Требования:
    - короткие абзацы
    - сильный hook
    - стиль TikTok AI creator
    - 80-120 слов
    - emoji
    - CTA в конце
    """

    text = await ask_groq(prompt)

    image_prompt = (
        f"cinematic AI future concept, {topic}, "
        "realistic, premium lighting, ultra detailed"
    )

    image = await generate_image(image_prompt)

    return text, image


# ====================================
# PUBLISH
# ====================================

async def publish_post():

    try:

        logger.info("Creating post...")

        text, image = await create_post()

        if image:

            await bot.send_photo(
                chat_id=CHANNEL_ID,
                photo=BufferedInputFile(
                    image,
                    filename="post.jpg"
                ),
                caption=text
            )

        else:

            await bot.send_message(
                chat_id=CHANNEL_ID,
                text=text
            )

        logger.info("Post published")

    except Exception as e:

        logger.error(e)


# ====================================
# COMMANDS
# ====================================

@dp.message(Command("start"))
async def start_handler(message: Message):

    if message.from_user.id != ADMIN_ID:
        return

    await message.answer(
        "🚀 PrimeOnix AI Bot работает!"
    )


@dp.message(Command("post"))
async def post_handler(message: Message):

    if message.from_user.id != ADMIN_ID:
        return

    await message.answer(
        "⏳ Создаю AI пост..."
    )

    await publish_post()

    await message.answer(
        "✅ Пост опубликован!"
    )


# ====================================
# SCHEDULER
# ====================================

def setup_scheduler():

    for time_str in POST_TIMES:

        hour, minute = map(
            int,
            time_str.split(":")
        )

        scheduler.add_job(
            publish_post,
            trigger="cron",
            hour=hour,
            minute=minute
        )


# ====================================
# MAIN
# ====================================

async def main():

    setup_scheduler()

    scheduler.start()

    logger.info("Bot started")

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
