import logging
import asyncio
from datetime import datetime
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
BOT_TOKEN  = "8925233625:AAE0lCKhErwAggy3HBal8VjO3TWXY5IFRzI"
CHANNEL_ID = "@primeonix26"
TIMEZONE   = "Europe/Moscow"
# ─────────────────────────────────────────────────────────────────────────────

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

bot       = Bot(token=BOT_TOKEN)
dp        = Dispatcher(storage=MemoryStorage())
scheduler = AsyncIOScheduler(timezone=TIMEZONE)

scheduled_posts: dict = {}
published_posts: dict = {}
post_counter = 0


# ─── СОСТОЯНИЯ ───────────────────────────────────────────────────────────────
class PostForm(StatesGroup):
    waiting_for_image    = State()
    waiting_for_text     = State()
    waiting_for_datetime = State()
    waiting_for_confirm  = State()

class EditForm(StatesGroup):
    choosing_field    = State()
    editing_text      = State()
    editing_image     = State()
    editing_datetime  = State()


# ─── КЛАВИАТУРЫ ──────────────────────────────────────────────────────────────
def main_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📝 Создать пост")],
            [KeyboardButton(text="📋 Мои посты"),     KeyboardButton(text="📰 Опубликованные")],
            [KeyboardButton(text="✏️ Редактировать"), KeyboardButton(text="❌ Отменить пост")],
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
            InlineKeyboardButton(text="👁 Предпросмотр",  callback_data="preview_post"),
            InlineKeyboardButton(text="✅ Подтвердить",   callback_data="confirm_post"),
        ],
        [InlineKeyboardButton(text="❌ Отменить создание", callback_data="cancel_post")]
    ])

def edit_field_keyboard(pid: int, is_published: bool = False):
    buttons = [
        [InlineKeyboardButton(text="✍️ Изменить текст", callback_data=f"edit_text_{pid}")],
        [InlineKeyboardButton(text="📸 Изменить фото",  callback_data=f"edit_photo_{pid}")],
    ]
    if not is_published:
        buttons.append([InlineKeyboardButton(text="⏰ Изменить время", callback_data=f"edit_time_{pid}")])
    buttons.append([InlineKeyboardButton(text="👁 Предпросмотр", callback_data=f"preview_{pid}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ─── РУКОВОДСТВО ПО ФОРМАТИРОВАНИЮ ───────────────────────────────────────────
def format_guide() -> str:
    return (
        "✍️ <b>Напиши текст поста.</b>\n\n"
        "Поддерживается HTML-форматирование:\n"
        "• <code>&lt;b&gt;текст&lt;/b&gt;</code> → <b>жирный</b>\n"
        "• <code>&lt;i&gt;текст&lt;/i&gt;</code> → <i>курсив</i>\n"
        "• <code>&lt;u&gt;текст&lt;/u&gt;</code> → <u>подчёркнутый</u>\n"
        "• <code>&lt;s&gt;текст&lt;/s&gt;</code> → <s>зачёркнутый</s>\n"
        "• <code>&lt;code&gt;текст&lt;/code&gt;</code> → <code>моноширинный</code>\n"
        "• <code>&lt;tg-spoiler&gt;текст&lt;/tg-spoiler&gt;</code> → скрытый спойлер\n\n"
        "<b>Пример:</b>\n"
        "<code>Привет! Это &lt;b&gt;жирный&lt;/b&gt; и &lt;i&gt;курсивный&lt;/i&gt; текст.</code>\n\n"
        "Напиши текст 👇"
    )


# ─── ПУБЛИКАЦИЯ ───────────────────────────────────────────────────────────────
async def publish_post(post_id: int):
    global published_posts
    post = scheduled_posts.get(post_id)
    if not post:
        return
    try:
        photo   = post.get("photo")
        text    = post.get("text", "")
        if photo:
            msg = await bot.send_photo(chat_id=CHANNEL_ID, photo=photo, caption=text, parse_mode="HTML")
        else:
            msg = await bot.send_message(chat_id=CHANNEL_ID, text=text, parse_mode="HTML")

        published_posts[post_id] = {
            **post,
            "message_id":   msg.message_id,
            "published_at": datetime.now(pytz.timezone(TIMEZONE)),
        }
        await bot.send_message(
            chat_id=post["creator_id"],
            text=f"✅ Пост <b>#{post_id}</b> опубликован!\n\nМожешь редактировать его через <b>«✏️ Редактировать»</b>",
            parse_mode="HTML",
            reply_markup=main_menu()
        )
        logger.info(f"Post #{post_id} published")
    except Exception as e:
        logger.error(f"Failed to publish post #{post_id}: {e}")
        await bot.send_message(chat_id=post["creator_id"], text=f"⚠️ Ошибка публикации поста #{post_id}: {e}")
    finally:
        scheduled_posts.pop(post_id, None)


# ─── /start ───────────────────────────────────────────────────────────────────
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "👋 <b>Привет! Я бот для планирования постов.</b>\n\n"
        "Что умею:\n"
        "• 📸 Принимать фото и текст\n"
        "• 🎨 Форматирование: <b>жирный</b>, <i>курсив</i>, <u>подчёркнутый</u> и др.\n"
        "• 👁 Предпросмотр поста перед публикацией\n"
        "• ⏰ Планировать время публикации\n"
        "• ✏️ Редактировать запланированные посты\n"
        "• 📰 Редактировать уже опубликованные посты\n\n"
        "Выбери действие 👇",
        parse_mode="HTML",
        reply_markup=main_menu()
    )


# ─── СОЗДАНИЕ ПОСТА ──────────────────────────────────────────────────────────
@dp.message(F.text == "📝 Создать пост")
async def create_post_start(message: types.Message, state: FSMContext):
    await state.clear()
    await state.set_state(PostForm.waiting_for_image)
    await message.answer(
        "📸 <b>Шаг 1/3 — Фотография</b>\n\nОтправь картинку или нажми кнопку ниже.",
        parse_mode="HTML",
        reply_markup=skip_keyboard()
    )

@dp.message(PostForm.waiting_for_image, F.photo)
async def received_image(message: types.Message, state: FSMContext):
    await state.update_data(photo=message.photo[-1].file_id)
    await state.set_state(PostForm.waiting_for_text)
    await message.answer("✅ Фото принято!\n\n" + format_guide(), parse_mode="HTML", reply_markup=ReplyKeyboardRemove())

@dp.message(PostForm.waiting_for_image, F.text == "⏩ Пропустить (без фото)")
async def skip_image(message: types.Message, state: FSMContext):
    await state.update_data(photo=None)
    await state.set_state(PostForm.waiting_for_text)
    await message.answer(format_guide(), parse_mode="HTML", reply_markup=ReplyKeyboardRemove())

@dp.message(PostForm.waiting_for_text, F.text)
async def received_text(message: types.Message, state: FSMContext):
    await state.update_data(text=message.text)
    await state.set_state(PostForm.waiting_for_datetime)
    tz  = pytz.timezone(TIMEZONE)
    now = datetime.now(tz).strftime("%d.%m.%Y %H:%M")
    await message.answer(
        f"✅ Текст принят!\n\n⏰ <b>Шаг 3/3 — Время публикации</b>\n\n"
        f"Сейчас: <code>{now}</code>\n\nФормат: <code>ДД.ММ.ГГГГ ЧЧ:ММ</code>\n"
        f"Пример: <code>25.12.2025 20:00</code>",
        parse_mode="HTML"
    )

@dp.message(PostForm.waiting_for_datetime, F.text)
async def received_datetime(message: types.Message, state: FSMContext):
    try:
        tz         = pytz.timezone(TIMEZONE)
        publish_dt = tz.localize(datetime.strptime(message.text.strip(), "%d.%m.%Y %H:%M"))
        if publish_dt <= datetime.now(tz):
            await message.answer("⚠️ Это время уже прошло! Введи будущее время.")
            return
        await state.update_data(publish_at=publish_dt.isoformat(), creator_id=message.from_user.id)
        await state.set_state(PostForm.waiting_for_confirm)
        data = await state.get_data()
        await message.answer(
            f"📋 <b>Пост готов к планированию</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"{'📸 Фото: прикреплено' if data.get('photo') else '📝 Без фото'}\n"
            f"⏰ <b>Время:</b> <code>{publish_dt.strftime('%d.%m.%Y в %H:%M')}</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Нажми <b>«👁 Предпросмотр»</b> чтобы увидеть как пост выглядит в канале.",
            parse_mode="HTML",
            reply_markup=confirm_keyboard()
        )
    except ValueError:
        await message.answer("❌ Неверный формат! Пример: <code>25.12.2025 18:30</code>", parse_mode="HTML")


# ─── ПРЕДПРОСМОТР ─────────────────────────────────────────────────────────────
@dp.callback_query(F.data == "preview_post", PostForm.waiting_for_confirm)
async def preview_new_post(callback: types.CallbackQuery, state: FSMContext):
    data  = await state.get_data()
    photo = data.get("photo")
    text  = data.get("text", "")
    await callback.answer()
    await callback.message.answer("👁 <b>Так пост будет выглядеть в канале:</b>", parse_mode="HTML")
    if photo:
        await callback.message.answer_photo(photo=photo, caption=text, parse_mode="HTML")
    else:
        await callback.message.answer(text, parse_mode="HTML")
    await callback.message.answer("Подтверди или отмени:", reply_markup=confirm_keyboard())

@dp.callback_query(F.data.startswith("preview_"))
async def preview_existing(callback: types.CallbackQuery):
    pid  = int(callback.data.split("_")[1])
    post = scheduled_posts.get(pid) or published_posts.get(pid)
    if not post:
        await callback.answer("Пост не найден.")
        return
    await callback.answer()
    photo = post.get("photo")
    text  = post.get("text", "")
    await callback.message.answer("👁 <b>Предпросмотр поста:</b>", parse_mode="HTML")
    if photo:
        await callback.message.answer_photo(photo=photo, caption=text, parse_mode="HTML")
    else:
        await callback.message.answer(text, parse_mode="HTML")


# ─── ПОДТВЕРЖДЕНИЕ ────────────────────────────────────────────────────────────
@dp.callback_query(F.data == "confirm_post", PostForm.waiting_for_confirm)
async def confirm_post(callback: types.CallbackQuery, state: FSMContext):
    global post_counter
    data = await state.get_data()
    await state.clear()
    post_counter += 1
    pid        = post_counter
    publish_dt = datetime.fromisoformat(data["publish_at"])
    scheduled_posts[pid] = {
        "photo":      data.get("photo"),
        "text":       data.get("text", ""),
        "publish_at": publish_dt,
        "creator_id": data["creator_id"],
    }
    scheduler.add_job(publish_post, trigger=DateTrigger(run_date=publish_dt), args=[pid], id=f"post_{pid}")
    await callback.message.edit_text(
        f"✅ <b>Пост #{pid} запланирован!</b>\n\n📅 <code>{publish_dt.strftime('%d.%m.%Y в %H:%M')}</code>",
        parse_mode="HTML"
    )
    await callback.message.answer("Что делаем дальше?", reply_markup=main_menu())
    await callback.answer()

@dp.callback_query(F.data == "cancel_post")
async def cancel_post_cb(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Создание поста отменено.")
    await callback.message.answer("Главное меню:", reply_markup=main_menu())
    await callback.answer()


# ─── МОИ ПОСТЫ ────────────────────────────────────────────────────────────────
@dp.message(F.text == "📋 Мои посты")
async def list_posts(message: types.Message):
    user_posts = {pid: p for pid, p in scheduled_posts.items() if p["creator_id"] == message.from_user.id}
    if not user_posts:
        await message.answer("📭 Нет запланированных постов.", reply_markup=main_menu())
        return
    text = "📋 <b>Запланированные посты:</b>\n\n"
    for pid, post in user_posts.items():
        dt      = post["publish_at"].strftime("%d.%m.%Y в %H:%M")
        icon    = "📸" if post.get("photo") else "📝"
        preview = (post["text"][:50] + "...") if len(post["text"]) > 50 else post["text"]
        text   += f"{icon} <b>Пост #{pid}</b> — ⏰ {dt}\n💬 {preview}\n\n"
    await message.answer(text, parse_mode="HTML", reply_markup=main_menu())


# ─── ОПУБЛИКОВАННЫЕ ───────────────────────────────────────────────────────────
@dp.message(F.text == "📰 Опубликованные")
async def list_published(message: types.Message):
    user_posts = {pid: p for pid, p in published_posts.items() if p["creator_id"] == message.from_user.id}
    if not user_posts:
        await message.answer("📭 Нет опубликованных постов.", reply_markup=main_menu())
        return
    text = "📰 <b>Опубликованные посты:</b>\n\n"
    for pid, post in user_posts.items():
        dt      = post["published_at"].strftime("%d.%m.%Y в %H:%M")
        icon    = "📸" if post.get("photo") else "📝"
        preview = (post["text"][:50] + "...") if len(post["text"]) > 50 else post["text"]
        text   += f"{icon} <b>Пост #{pid}</b> — 📅 {dt}\n💬 {preview}\n\n"
    await message.answer(text, parse_mode="HTML", reply_markup=main_menu())


# ─── ОТМЕНА ПОСТА ─────────────────────────────────────────────────────────────
@dp.message(F.text == "❌ Отменить пост")
async def cancel_post_menu(message: types.Message):
    user_posts = {pid: p for pid, p in scheduled_posts.items() if p["creator_id"] == message.from_user.id}
    if not user_posts:
        await message.answer("📭 Нет постов для отмены.", reply_markup=main_menu())
        return
    buttons = [[InlineKeyboardButton(
        text=f"❌ Пост #{pid} — {p['publish_at'].strftime('%d.%m %H:%M')}",
        callback_data=f"delete_{pid}"
    )] for pid, p in user_posts.items()]
    await message.answer("Выбери пост для отмены:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@dp.callback_query(F.data.startswith("delete_"))
async def delete_post(callback: types.CallbackQuery):
    pid = int(callback.data.split("_")[1])
    if pid in scheduled_posts and scheduled_posts[pid]["creator_id"] == callback.from_user.id:
        try:
            scheduler.remove_job(f"post_{pid}")
        except Exception:
            pass
        scheduled_posts.pop(pid, None)
        await callback.message.edit_text(f"✅ Пост <b>#{pid}</b> отменён.", parse_mode="HTML")
    else:
        await callback.message.edit_text("⚠️ Пост не найден.")
    await callback.answer()


# ─── РЕДАКТИРОВАНИЕ ───────────────────────────────────────────────────────────
@dp.message(F.text == "✏️ Редактировать")
async def edit_menu(message: types.Message):
    uid        = message.from_user.id
    user_sched = {pid: p for pid, p in scheduled_posts.items() if p["creator_id"] == uid}
    user_pub   = {pid: p for pid, p in published_posts.items()  if p["creator_id"] == uid}

    if not user_sched and not user_pub:
        await message.answer("📭 Нет постов для редактирования.", reply_markup=main_menu())
        return

    buttons = []
    if user_sched:
        buttons.append([InlineKeyboardButton(text="─── 📋 Запланированные ───", callback_data="noop")])
        for pid, p in user_sched.items():
            dt = p["publish_at"].strftime("%d.%m %H:%M")
            buttons.append([InlineKeyboardButton(text=f"✏️ Пост #{pid} — ⏰ {dt}", callback_data=f"editsel_{pid}_0")])
    if user_pub:
        buttons.append([InlineKeyboardButton(text="─── 📰 Опубликованные ───", callback_data="noop")])
        for pid, p in user_pub.items():
            dt = p["published_at"].strftime("%d.%m %H:%M")
            buttons.append([InlineKeyboardButton(text=f"✏️ Пост #{pid} — 📅 {dt}", callback_data=f"editsel_{pid}_1")])

    await message.answer("Выбери пост для редактирования:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@dp.callback_query(F.data == "noop")
async def noop(callback: types.CallbackQuery):
    await callback.answer()

@dp.callback_query(F.data.startswith("editsel_"))
async def edit_select(callback: types.CallbackQuery, state: FSMContext):
    parts  = callback.data.split("_")
    pid    = int(parts[1])
    is_pub = parts[2] == "1"
    post   = published_posts.get(pid) if is_pub else scheduled_posts.get(pid)
    if not post:
        await callback.answer("Пост не найден.")
        return

    await state.update_data(editing_pid=pid, is_published=is_pub)
    await state.set_state(EditForm.choosing_field)

    icon    = "📸" if post.get("photo") else "📝"
    preview = (post["text"][:60] + "...") if len(post["text"]) > 60 else post["text"]
    status  = f"📅 Опубликован: {post['published_at'].strftime('%d.%m.%Y %H:%M')}" if is_pub else f"⏰ Запланирован: {post['publish_at'].strftime('%d.%m.%Y %H:%M')}"

    await callback.message.edit_text(
        f"✏️ <b>Редактирование поста #{pid}</b>\n\n{icon} {status}\n💬 {preview}\n\nЧто изменить?",
        parse_mode="HTML",
        reply_markup=edit_field_keyboard(pid, is_pub)
    )
    await callback.answer()

# Изменить текст
@dp.callback_query(F.data.startswith("edit_text_"))
async def edit_text_start(callback: types.CallbackQuery, state: FSMContext):
    pid = int(callback.data.split("_")[2])
    await state.update_data(editing_pid=pid)
    await state.set_state(EditForm.editing_text)
    await callback.message.answer("✍️ <b>Введи новый текст поста:</b>\n\n" + format_guide(), parse_mode="HTML")
    await callback.answer()

@dp.message(EditForm.editing_text, F.text)
async def edit_text_save(message: types.Message, state: FSMContext):
    data     = await state.get_data()
    pid      = data["editing_pid"]
    is_pub   = data.get("is_published", False)
    new_text = message.text

    if is_pub and pid in published_posts:
        published_posts[pid]["text"] = new_text
        post = published_posts[pid]
        try:
            if post.get("photo"):
                await bot.edit_message_caption(chat_id=CHANNEL_ID, message_id=post["message_id"], caption=new_text, parse_mode="HTML")
            else:
                await bot.edit_message_text(chat_id=CHANNEL_ID, message_id=post["message_id"], text=new_text, parse_mode="HTML")
            await message.answer(f"✅ Текст поста <b>#{pid}</b> обновлён в канале!", parse_mode="HTML", reply_markup=main_menu())
        except Exception as e:
            await message.answer(f"⚠️ Ошибка: {e}", reply_markup=main_menu())
    elif pid in scheduled_posts:
        scheduled_posts[pid]["text"] = new_text
        await message.answer(f"✅ Текст поста <b>#{pid}</b> обновлён!", parse_mode="HTML", reply_markup=main_menu())
    else:
        await message.answer("⚠️ Пост не найден.", reply_markup=main_menu())
    await state.clear()

# Изменить фото
@dp.callback_query(F.data.startswith("edit_photo_"))
async def edit_photo_start(callback: types.CallbackQuery, state: FSMContext):
    pid = int(callback.data.split("_")[2])
    await state.update_data(editing_pid=pid)
    await state.set_state(EditForm.editing_image)
    await callback.message.answer("📸 Отправь новое фото:")
    await callback.answer()

@dp.message(EditForm.editing_image, F.photo)
async def edit_photo_save(message: types.Message, state: FSMContext):
    data      = await state.get_data()
    pid       = data["editing_pid"]
    is_pub    = data.get("is_published", False)
    new_photo = message.photo[-1].file_id

    if is_pub and pid in published_posts:
        published_posts[pid]["photo"] = new_photo
        await message.answer(f"✅ Фото обновлено в базе поста <b>#{pid}</b>.\n\n⚠️ Telegram не позволяет менять медиафайл в уже опубликованном сообщении — изменение сохранено для следующей публикации.", parse_mode="HTML", reply_markup=main_menu())
    elif pid in scheduled_posts:
        scheduled_posts[pid]["photo"] = new_photo
        await message.answer(f"✅ Фото поста <b>#{pid}</b> обновлено!", parse_mode="HTML", reply_markup=main_menu())
    else:
        await message.answer("⚠️ Пост не найден.", reply_markup=main_menu())
    await state.clear()

# Изменить время
@dp.callback_query(F.data.startswith("edit_time_"))
async def edit_time_start(callback: types.CallbackQuery, state: FSMContext):
    pid = int(callback.data.split("_")[2])
    await state.update_data(editing_pid=pid)
    await state.set_state(EditForm.editing_datetime)
    tz  = pytz.timezone(TIMEZONE)
    now = datetime.now(tz).strftime("%d.%m.%Y %H:%M")
    await callback.message.answer(
        f"⏰ <b>Введи новое время публикации:</b>\n\nСейчас: <code>{now}</code>\nФормат: <code>ДД.ММ.ГГГГ ЧЧ:ММ</code>",
        parse_mode="HTML"
    )
    await callback.answer()

@dp.message(EditForm.editing_datetime, F.text)
async def edit_time_save(message: types.Message, state: FSMContext):
    data = await state.get_data()
    pid  = data["editing_pid"]
    try:
        tz         = pytz.timezone(TIMEZONE)
        publish_dt = tz.localize(datetime.strptime(message.text.strip(), "%d.%m.%Y %H:%M"))
        if publish_dt <= datetime.now(tz):
            await message.answer("⚠️ Это время уже прошло! Введи будущее время.")
            return
        if pid in scheduled_posts:
            scheduled_posts[pid]["publish_at"] = publish_dt
            try:
                scheduler.remove_job(f"post_{pid}")
            except Exception:
                pass
            scheduler.add_job(publish_post, trigger=DateTrigger(run_date=publish_dt), args=[pid], id=f"post_{pid}")
            await message.answer(
                f"✅ Время поста <b>#{pid}</b> обновлено!\n📅 <code>{publish_dt.strftime('%d.%m.%Y в %H:%M')}</code>",
                parse_mode="HTML", reply_markup=main_menu()
            )
        else:
            await message.answer("⚠️ Пост не найден.", reply_markup=main_menu())
    except ValueError:
        await message.answer("❌ Неверный формат! Пример: <code>25.12.2025 18:30</code>", parse_mode="HTML")
        return
    await state.clear()


# ─── ЗАПУСК ───────────────────────────────────────────────────────────────────
async def main():
    scheduler.start()
    logger.info("Bot started. Scheduler running.")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
