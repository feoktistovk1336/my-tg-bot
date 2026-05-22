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
from aiogram.types import *

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger


# ================= CONFIG =================
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))
ADMIN_ID = int(os.getenv("ADMIN_ID"))
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

TZ = pytz.timezone("Europe/Moscow")

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
scheduler = AsyncIOScheduler(timezone=TZ)


# ================= DATABASE (RAM MVP) =================
posts = {}          # scheduled
published = {}
failed = {}
templates = {}

counter = 0


# ================= STATES =================
class PostFSM(StatesGroup):
    text = State()
    datetime = State()
    media = State()


class EditFSM(StatesGroup):
    text = State()


# ================= AI =================
TOPICS = [
    "AI заменяет дизайнеров",
    "Нейросети в бизнесе",
    "Будущее контента",
    "AI видео революция",
    "Автоматизация заработка",
]


async def ask_groq(prompt: str):
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {"role": "system", "content": "Ты вирусный Telegram контент-креатор."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.9
    }

    async with aiohttp.ClientSession() as s:
        async with s.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers=headers,
            json=payload
        ) as r:
            data = await r.json()
            return data["choices"][0]["message"]["content"]


async def generate_post():
    topic = random.choice(TOPICS)

    return await ask_groq(f"""
    Напиши вирусный Telegram пост.
    Тема: {topic}

    - 80–120 слов
    - сильный hook
    - emoji
    - CTA
    - стиль TikTok AI creator
    """)


# ================= KEYBOARD =================
def menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🤖 AI пост"), KeyboardButton(text="🧠 Контент-план")],
            [KeyboardButton(text="📝 Создать пост"), KeyboardButton(text="📋 Посты")],
            [KeyboardButton(text="📊 Статистика"), KeyboardButton(text="💾 Шаблоны")],
        ],
        resize_keyboard=True
    )


def confirm_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Опубликовать", callback_data="publish")],
        [InlineKeyboardButton(text="⏰ Запланировать", callback_data="schedule")],
        [InlineKeyboardButton(text="💾 Шаблон", callback_data="template")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]
    ])


# ================= UTIL =================
def parse_dt(text: str):
    dt = datetime.strptime(text, "%d.%m.%Y %H:%M")
    return TZ.localize(dt)


async def send_post(pid: int):
    post = posts.get(pid)
    if not post:
        return

    try:
        await bot.send_message(CHANNEL_ID, post["text"])
        published[pid] = post
        posts.pop(pid, None)
    except Exception as e:
        failed[pid] = post


# ================= START =================
@dp.message(Command("start"))
async def start(m: Message):
    if m.from_user.id != ADMIN_ID:
        return
    await m.answer("🚀 SaaS Bot V3 запущен", reply_markup=menu())


# ================= AI POST =================
@dp.message(F.text == "🤖 AI пост")
async def ai_post(m: Message, state: FSMContext):
    text = await generate_post()
    await state.update_data(text=text)
    await m.answer(text, reply_markup=confirm_kb())


# ================= CONTENT PLAN =================
@dp.message(F.text == "🧠 Контент-план")
async def plan(m: Message):
    plan = "\n".join([f"• {t}" for t in TOPICS])
    await m.answer(f"🧠 Контент-план:\n\n{plan}")


# ================= CREATE POST =================
@dp.message(F.text == "📝 Создать пост")
async def create(m: Message, state: FSMContext):
    await state.set_state(PostFSM.text)
    await m.answer("✍️ Введи текст")


@dp.message(PostFSM.text)
async def get_text(m: Message, state: FSMContext):
    await state.update_data(text=m.text)
    await state.set_state(PostFSM.datetime)
    await m.answer("⏰ Дата (ДД.ММ.ГГГГ ЧЧ:ММ)")


@dp.message(PostFSM.datetime)
async def get_time(m: Message, state: FSMContext):
    global counter

    try:
        dt = parse_dt(m.text)

        data = await state.get_data()
        await state.clear()

        counter += 1
        pid = counter

        posts[pid] = {
            "text": data["text"],
            "time": dt
        }

        scheduler.add_job(send_post, DateTrigger(run_date=dt), args=[pid], id=str(pid))

        await m.answer(f"✅ Пост #{pid} запланирован", reply_markup=menu())

    except Exception:
        await m.answer("❌ Неверный формат")


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
        f"📊 SaaS Stats:\n\n"
        f"📋 scheduled: {len(posts)}\n"
        f"✅ published: {len(published)}\n"
        f"⚠️ failed: {len(failed)}\n"
        f"💾 templates: {len(templates)}"
    )


# ================= TEMPLATES =================
@dp.message(F.text == "💾 Шаблоны")
async def show_templates(m: Message):
    if not templates:
        await m.answer("Нет шаблонов")
        return

    text = "\n".join([f"• {k}" for k in templates.keys()])
    await m.answer(f"💾 Шаблоны:\n\n{text}")


# ================= CALLBACKS =================
@dp.callback_query(F.data == "publish")
async def publish(c: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await state.clear()

    await bot.send_message(CHANNEL_ID, data["text"])
    await c.message.edit_text("🚀 Опубликовано")


@dp.callback_query(F.data == "schedule")
async def schedule(c: CallbackQuery):
    await c.message.answer("Используй планирование через меню")
    await c.answer()


@dp.callback_query(F.data == "template")
async def template(c: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    templates[f"tpl_{len(templates)+1}"] = data
    await c.message.edit_text("💾 Сохранено в шаблоны")


@dp.callback_query(F.data == "cancel")
async def cancel(c: CallbackQuery, state: FSMContext):
    await state.clear()
    await c.message.edit_text("❌ Отменено")


# ================= MAIN =================
async def main():
    scheduler.start()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
