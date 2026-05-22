import os
import asyncio
import random
import logging
from datetime import datetime

import aiohttp
import pytz

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardRemove
)

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger


# ================= CONFIG =================
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))
ADMIN_ID = int(os.getenv("ADMIN_ID"))
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

TZ = pytz.timezone("Europe/Moscow")


# ================= INIT =================
logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
scheduler = AsyncIOScheduler(timezone=TZ)

posts = {}
published = {}
counter = 0


# ================= STATES =================
class PostFSM(StatesGroup):
    text = State()
    time = State()


# ================= AI =================
TOPICS = [
    "AI заменяет дизайнеров",
    "Будущее нейросетей",
    "AI видео генерация",
    "Топ AI инструментов",
    "Нейросети и деньги",
    "Автоматизация бизнеса с AI",
]


async def ask_groq(prompt: str):
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }

    json_data = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {"role": "system", "content": "Ты вирусный Telegram копирайтер."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.9
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers=headers,
            json=json_data
        ) as r:
            data = await r.json()
            return data["choices"][0]["message"]["content"]


async def generate_post():
    topic = random.choice(TOPICS)

    prompt = f"""
    Напиши вирусный Telegram пост.
    Тема: {topic}

    Требования:
    - 80-120 слов
    - сильный хук
    - emoji
    - стиль TikTok AI creator
    - CTA в конце
    """

    return await ask_groq(prompt)


# ================= KEYBOARD =================
def menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🤖 AI пост")],
            [KeyboardButton(text="📝 Создать пост")],
            [KeyboardButton(text="📋 Посты"), KeyboardButton(text="📊 Статистика")]
        ],
        resize_keyboard=True
    )


def confirm_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Опубликовать", callback_data="publish")],
        [InlineKeyboardButton(text="⏰ Запланировать", callback_data="schedule")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]
    ])


# ================= START =================
@dp.message(Command("start"))
async def start(m: Message):
    if m.from_user.id != ADMIN_ID:
        return
    await m.answer("🚀 AI Bot V2 запущен", reply_markup=menu())


# ================= AI POST =================
@dp.message(F.text == "🤖 AI пост")
async def ai_post(m: Message, state: FSMContext):
    text = await generate_post()

    await state.update_data(text=text)

    await m.answer(
        f"🤖 AI сгенерировал пост:\n\n{text}",
        reply_markup=confirm_kb()
    )


# ================= MANUAL POST =================
@dp.message(F.text == "📝 Создать пост")
async def manual(m: Message, state: FSMContext):
    await state.set_state(PostFSM.text)
    await m.answer("Введи текст:", reply_markup=ReplyKeyboardRemove())


@dp.message(PostFSM.text)
async def get_text(m: Message, state: FSMContext):
    await state.update_data(text=m.text)
    await state.set_state(PostFSM.time)
    await m.answer("⏰ Введи время (ДД.ММ.ГГГГ ЧЧ:ММ)")


@dp.message(PostFSM.time)
async def get_time(m: Message, state: FSMContext):
    try:
        dt = datetime.strptime(m.text, "%d.%m.%Y %H:%M")
        dt = TZ.localize(dt)

        data = await state.get_data()
        await state.clear()

        global counter
        counter += 1
        pid = counter

        posts[pid] = {
            "text": data["text"],
            "time": dt
        }

        scheduler.add_job(send_post, DateTrigger(run_date=dt), args=[pid], id=str(pid))

        await m.answer(f"✅ Пост #{pid} запланирован", reply_markup=menu())

    except Exception:
        await m.answer("❌ Формат: 25.12.2026 18:30")


# ================= SEND POST =================
async def send_post(pid: int):
    post = posts.get(pid)
    if not post:
        return

    await bot.send_message(CHANNEL_ID, post["text"])

    published[pid] = post
    posts.pop(pid, None)


# ================= LIST =================
@dp.message(F.text == "📋 Посты")
async def list_posts(m: Message):
    if not posts:
        await m.answer("Нет постов")
        return

    text = "📋 Посты:\n\n"
    for pid, p in posts.items():
        text += f"#{pid} — {p['time'].strftime('%d.%m %H:%M')}\n"

    await m.answer(text)


# ================= STATS =================
@dp.message(F.text == "📊 Статистика")
async def stats(m: Message):
    await m.answer(
        f"📊 Статистика:\n\n"
        f"📋 Запланировано: {len(posts)}\n"
        f"✅ Опубликовано: {len(published)}"
    )


# ================= CALLBACKS =================
@dp.callback_query(F.data == "publish")
async def publish(call: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await state.clear()

    await bot.send_message(CHANNEL_ID, data["text"])

    await call.message.edit_text("✅ Опубликовано")
    await call.answer()


@dp.callback_query(F.data == "schedule")
async def schedule(call: types.CallbackQuery):
    await call.message.answer("Используй '📝 Создать пост'")
    await call.answer()


@dp.callback_query(F.data == "cancel")
async def cancel(call: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text("❌ Отменено")
    await call.answer()


# ================= MAIN =================
async def main():
    scheduler.start()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
