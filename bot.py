import logging
import asyncio
from datetime import datetime
from typing import Optional
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardRemove
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger
import pytz

# ─── НАСТРОЙКИ ───────────────────────────────────────────────────────────────
BOT_TOKEN = "8925233625:AAE0lCKhErwAggy3HBal8VjO3TWXY5IFRzI"          # Получить у @BotFather
CHANNEL_ID = "@primeonix26"     # Например: @mychannel или -100123456789
TIMEZONE = "Europe/Moscow"             # Ваш часовой пояс
# ─────────────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
scheduler = AsyncIOScheduler(timezone=TIMEZONE)

# Хранилище запланированных постов (в памяти)
scheduled_posts: dict = {}
post_counter = 0


# ─── СОСТОЯНИЯ FSM ───────────────────────────────────────────────────────────
class PostForm(StatesGroup):
    waiting_for_image    = State()
    waiting_for_text     = State()
    waiting_for_datetime = State()
    waiting_for_confirm  = State()


# ─── КЛАВИАТУРЫ ──────────────────────────────────────────────────────────────
def main_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📝 Создать пост")],
            [KeyboardButton(text="📋 Мои посты"), KeyboardButton(text="❌ Отменить пост")],
        ],
        resize_keyboard=True
    )

def skip_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="⏩ Пропустить (без фото)")]],
        resize_keyboard=True
    )

def confirm_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Подтвердить", callback_data="confirm_post"),
            InlineKeyboardButton(text="❌ Отменить",   callback_data="cancel_post"),
        ]
    ])


# ─── ПУБЛИКАЦИЯ ПОСТА ────────────────────────────────────────────────────────
async def publish_post(post_id: int):
    """Отправляет пост в канал в назначенное время."""
    post = scheduled_posts.get(post_id)
    if not post:
        return

    try:
        caption = post.get("text", "")
        photo   = post.get("photo")

        if photo:
            await bot.send_photo(
                chat_id=CHANNEL_ID,
                photo=photo,
                caption=caption,
                parse_mode="HTML"
            )
        else:
            await bot.send_message(
                chat_id=CHANNEL_ID,
                text=caption,
                parse_mode="HTML"
            )

        # Уведомить создателя
        await bot.send_message(
            chat_id=post["creator_id"],
            text=f"✅ Пост <b>#{post_id}</b> успешно опубликован в канал!",
            parse_mode="HTML"
        )
        logger.info(f"Post #{post_id} published to {CHANNEL_ID}")

    except Exception as e:
        logger.error(f"Failed to publish post #{post_id}: {e}")
        await bot.send_message(
            chat_id=post["creator_id"],
            text=f"⚠️ Ошибка при публикации поста <b>#{post_id}</b>: {e}",
            parse_mode="HTML"
        )
    finally:
        scheduled_posts.pop(post_id, None)


# ─── КОМАНДЫ ─────────────────────────────────────────────────────────────────
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "👋 <b>Привет! Я бот для планирования постов.</b>\n\n"
        "Я помогу тебе:\n"
        "• 📸 Добавить картинку к посту\n"
        "• ✍️ Написать описание\n"
        "• ⏰ Запланировать время публикации\n\n"
        "Выбери действие в меню ниже 👇",
        parse_mode="HTML",
        reply_markup=main_menu()
    )

@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    await message.answer(
        "📖 <b>Как пользоваться ботом:</b>\n\n"
        "1️⃣ Нажми <b>«Создать пост»</b>\n"
        "2️⃣ Отправь картинку (или пропусти)\n"
        "3️⃣ Напиши текст поста\n"
        "4️⃣ Укажи дату и время в формате:\n"
        "   <code>ДД.ММ.ГГГГ ЧЧ:ММ</code>\n"
        "   Например: <code>25.12.2025 18:30</code>\n"
        "5️⃣ Подтверди публикацию\n\n"
        "⚡ Пост автоматически уйдёт в канал в указанное время!",
        parse_mode="HTML"
    )


# ─── СОЗДАНИЕ ПОСТА ──────────────────────────────────────────────────────────
@dp.message(F.text == "📝 Создать пост")
async def create_post_start(message: types.Message, state: FSMContext):
    await state.clear()
    await state.set_state(PostForm.waiting_for_image)
    await message.answer(
        "📸 <b>Шаг 1/3 — Фотография</b>\n\n"
        "Отправь картинку для поста.\n"
        "Если пост без фото — нажми кнопку ниже.",
        parse_mode="HTML",
        reply_markup=skip_keyboard()
    )

@dp.message(PostForm.waiting_for_image, F.photo)
async def received_image(message: types.Message, state: FSMContext):
    photo_id = message.photo[-1].file_id
    await state.update_data(photo=photo_id)
    await state.set_state(PostForm.waiting_for_text)
    await message.answer(
        "✅ Фото принято!\n\n"
        "✍️ <b>Шаг 2/3 — Текст поста</b>\n\n"
        "Напиши описание или текст для поста.\n"
        "Поддерживается HTML-разметка: <b>жирный</b>, <i>курсив</i>",
        parse_mode="HTML",
        reply_markup=ReplyKeyboardRemove()
    )

@dp.message(PostForm.waiting_for_image, F.text == "⏩ Пропустить (без фото)")
async def skip_image(message: types.Message, state: FSMContext):
    await state.update_data(photo=None)
    await state.set_state(PostForm.waiting_for_text)
    await message.answer(
        "⏩ Пост будет без фото.\n\n"
        "✍️ <b>Шаг 2/3 — Текст поста</b>\n\n"
        "Напиши описание или текст для поста.",
        parse_mode="HTML",
        reply_markup=ReplyKeyboardRemove()
    )

@dp.message(PostForm.waiting_for_text, F.text)
async def received_text(message: types.Message, state: FSMContext):
    await state.update_data(text=message.text)
    await state.set_state(PostForm.waiting_for_datetime)
    tz = pytz.timezone(TIMEZONE)
    now = datetime.now(tz).strftime("%d.%m.%Y %H:%M")
    await message.answer(
        "✅ Текст принят!\n\n"
        "⏰ <b>Шаг 3/3 — Дата и время публикации</b>\n\n"
        f"Текущее время: <code>{now}</code>\n\n"
        "Введи дату и время в формате:\n"
        "<code>ДД.ММ.ГГГГ ЧЧ:ММ</code>\n\n"
        "Например: <code>25.12.2025 20:00</code>",
        parse_mode="HTML"
    )

@dp.message(PostForm.waiting_for_datetime, F.text)
async def received_datetime(message: types.Message, state: FSMContext):
    try:
        tz = pytz.timezone(TIMEZONE)
        publish_dt = datetime.strptime(message.text.strip(), "%d.%m.%Y %H:%M")
        publish_dt = tz.localize(publish_dt)

        if publish_dt <= datetime.now(tz):
            await message.answer(
                "⚠️ Это время уже прошло! Введи будущую дату и время.",
                parse_mode="HTML"
            )
            return

        await state.update_data(
            publish_at=publish_dt.isoformat(),
            creator_id=message.from_user.id
        )
        await state.set_state(PostForm.waiting_for_confirm)

        data  = await state.get_data()
        photo = data.get("photo")
        text  = data.get("text", "")

        preview = (
            "👁 <b>Предпросмотр поста:</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"{'📸 Фото: прикреплено' if photo else '📝 Без фото'}\n\n"
            f"<b>Текст:</b>\n{text}\n\n"
            f"⏰ <b>Время публикации:</b>\n"
            f"<code>{publish_dt.strftime('%d.%m.%Y в %H:%M')}</code>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "Подтверди или отмени:"
        )
        await message.answer(preview, parse_mode="HTML", reply_markup=confirm_keyboard())

    except ValueError:
        await message.answer(
            "❌ Неверный формат! Используй:\n"
            "<code>ДД.ММ.ГГГГ ЧЧ:ММ</code>\n\n"
            "Например: <code>25.12.2025 18:30</code>",
            parse_mode="HTML"
        )


# ─── ПОДТВЕРЖДЕНИЕ / ОТМЕНА ──────────────────────────────────────────────────
@dp.callback_query(F.data == "confirm_post", PostForm.waiting_for_confirm)
async def confirm_post(callback: types.CallbackQuery, state: FSMContext):
    global post_counter
    data = await state.get_data()
    await state.clear()

    post_counter += 1
    pid = post_counter

    publish_dt = datetime.fromisoformat(data["publish_at"])
    scheduled_posts[pid] = {
        "photo":      data.get("photo"),
        "text":       data.get("text", ""),
        "publish_at": publish_dt,
        "creator_id": data["creator_id"],
    }

    scheduler.add_job(
        publish_post,
        trigger=DateTrigger(run_date=publish_dt),
        args=[pid],
        id=f"post_{pid}"
    )

    await callback.message.edit_text(
        f"✅ <b>Пост #{pid} запланирован!</b>\n\n"
        f"📅 Дата: <code>{publish_dt.strftime('%d.%m.%Y')}</code>\n"
        f"⏰ Время: <code>{publish_dt.strftime('%H:%M')}</code>\n\n"
        "Я напомню тебе после публикации 🚀",
        parse_mode="HTML"
    )
    await callback.message.answer("Что делаем дальше?", reply_markup=main_menu())
    await callback.answer()

@dp.callback_query(F.data == "cancel_post")
async def cancel_post_callback(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Создание поста отменено.")
    await callback.message.answer("Что делаем дальше?", reply_markup=main_menu())
    await callback.answer()


# ─── МОИ ПОСТЫ ───────────────────────────────────────────────────────────────
@dp.message(F.text == "📋 Мои посты")
async def list_posts(message: types.Message):
    user_posts = {
        pid: post for pid, post in scheduled_posts.items()
        if post["creator_id"] == message.from_user.id
    }

    if not user_posts:
        await message.answer(
            "📭 У тебя нет запланированных постов.\n\n"
            "Нажми <b>«Создать пост»</b> чтобы добавить первый!",
            parse_mode="HTML",
            reply_markup=main_menu()
        )
        return

    text = "📋 <b>Твои запланированные посты:</b>\n\n"
    for pid, post in user_posts.items():
        dt   = post["publish_at"].strftime("%d.%m.%Y в %H:%M")
        has_photo = "📸" if post.get("photo") else "📝"
        preview   = (post["text"][:40] + "...") if len(post["text"]) > 40 else post["text"]
        text += f"{has_photo} <b>Пост #{pid}</b>\n⏰ {dt}\n💬 {preview}\n\n"

    await message.answer(text, parse_mode="HTML", reply_markup=main_menu())


# ─── ОТМЕНА ПОСТА ────────────────────────────────────────────────────────────
@dp.message(F.text == "❌ Отменить пост")
async def cancel_post_menu(message: types.Message):
    user_posts = {
        pid: post for pid, post in scheduled_posts.items()
        if post["creator_id"] == message.from_user.id
    }

    if not user_posts:
        await message.answer("📭 Нет постов для отмены.", reply_markup=main_menu())
        return

    buttons = [
        [InlineKeyboardButton(
            text=f"❌ Пост #{pid} — {post['publish_at'].strftime('%d.%m %H:%M')}",
            callback_data=f"delete_{pid}"
        )]
        for pid, post in user_posts.items()
    ]
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer("Выбери пост для отмены:", reply_markup=keyboard)

@dp.callback_query(F.data.startswith("delete_"))
async def delete_post(callback: types.CallbackQuery):
    pid = int(callback.data.split("_")[1])

    if pid in scheduled_posts and scheduled_posts[pid]["creator_id"] == callback.from_user.id:
        try:
            scheduler.remove_job(f"post_{pid}")
        except Exception:
            pass
        scheduled_posts.pop(pid, None)
        await callback.message.edit_text(f"✅ Пост <b>#{pid}</b> отменён и удалён.", parse_mode="HTML")
    else:
        await callback.message.edit_text("⚠️ Пост не найден или уже опубликован.")

    await callback.answer()


# ─── ЗАПУСК ──────────────────────────────────────────────────────────────────
async def main():
    scheduler.start()
    logger.info("Bot started. Scheduler running.")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
