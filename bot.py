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
    ReplyKeyboardRemove, InputMediaPhoto,
    InputMediaVideo, InputMediaAudio
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
failed_posts: dict    = {}
templates: dict       = {}
post_counter          = 0
stats                 = {"published": 0, "failed": 0, "cancelled": 0}
 
 
# ─── СОСТОЯНИЯ ───────────────────────────────────────────────────────────────
class PostForm(StatesGroup):
    choosing_media_type  = State()
    waiting_for_photos   = State()
    waiting_for_videos   = State()
    waiting_for_music    = State()
    waiting_for_text     = State()
    waiting_for_datetime = State()
    waiting_for_confirm  = State()
 
class EditForm(StatesGroup):
    choosing_field   = State()
    editing_text     = State()
    editing_media    = State()
    editing_datetime = State()
 
class DraftEdit(StatesGroup):
    editing_text     = State()
    editing_media    = State()
    editing_datetime = State()
 
class TemplateForm(StatesGroup):
    waiting_name = State()
 
class RepeatForm(StatesGroup):
    waiting_datetime = State()
 
 
# ─── КЛАВИАТУРЫ ──────────────────────────────────────────────────────────────
def main_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📝 Создать пост")],
            [KeyboardButton(text="📋 Мои посты"),     KeyboardButton(text="📰 Опубликованные")],
            [KeyboardButton(text="⚠️ Ошибки постов"), KeyboardButton(text="✏️ Редактировать")],
            [KeyboardButton(text="📅 Расписание"),     KeyboardButton(text="📊 Статистика")],
            [KeyboardButton(text="⏱ Шаблоны"),        KeyboardButton(text="❌ Отменить пост")],
        ],
        resize_keyboard=True
    )
 
def media_type_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🖼 Фото (до 10 шт)",   callback_data="media_photos")],
        [InlineKeyboardButton(text="🎬 Видео (до 5 шт)",   callback_data="media_videos")],
        [InlineKeyboardButton(text="🎵 Музыка (1 трек)",   callback_data="media_music")],
        [InlineKeyboardButton(text="📝 Только текст",       callback_data="media_none")],
    ])
 
def more_media_keyboard(count: int, max_count: int, media_type: str):
    type_name = {"photos": "фото", "videos": "видео", "music": "музыку"}.get(media_type, "файл")
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=f"➡️ Достаточно ({count}/{max_count})")],
        ],
        resize_keyboard=True
    )
 
def confirm_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👁 Предпросмотр",      callback_data="preview_post")],
        [
            InlineKeyboardButton(text="✍️ Текст",  callback_data="edit_draft_text"),
            InlineKeyboardButton(text="📎 Медиа",  callback_data="edit_draft_media"),
            InlineKeyboardButton(text="⏰ Время",  callback_data="edit_draft_time"),
        ],
        [
            InlineKeyboardButton(text="💾 Шаблон",      callback_data="save_template"),
            InlineKeyboardButton(text="✅ Подтвердить", callback_data="confirm_post"),
        ],
        [InlineKeyboardButton(text="❌ Отменить создание", callback_data="cancel_post")],
    ])
 
def formatting_keyboard():
    """Кнопки форматирования текста."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="𝐁 Жирный",        callback_data="fmt_bold"),
            InlineKeyboardButton(text="𝐼 Курсив",         callback_data="fmt_italic"),
        ],
        [
            InlineKeyboardButton(text="U Подчёркнутый",   callback_data="fmt_underline"),
            InlineKeyboardButton(text="S Зачёркнутый",    callback_data="fmt_strike"),
        ],
        [
            InlineKeyboardButton(text="|| Спойлер",       callback_data="fmt_spoiler"),
            InlineKeyboardButton(text="<> Код",           callback_data="fmt_code"),
        ],
        [InlineKeyboardButton(text="✅ Текст готов",      callback_data="fmt_done")],
    ])
 
def edit_field_keyboard(pid: int, is_published: bool = False):
    buttons = [
        [InlineKeyboardButton(text="✍️ Изменить текст",  callback_data=f"edit_text_{pid}")],
        [InlineKeyboardButton(text="📎 Изменить медиа",  callback_data=f"edit_photo_{pid}")],
    ]
    if not is_published:
        buttons.append([InlineKeyboardButton(text="⏰ Изменить время",  callback_data=f"edit_time_{pid}")])
        buttons.append([InlineKeyboardButton(text="🔁 Перепланировать", callback_data=f"replan_{pid}")])
    buttons.append([InlineKeyboardButton(text="👁 Предпросмотр",         callback_data=f"preview_{pid}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)
 
def failed_post_keyboard(pid: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✍️ Редактировать текст", callback_data=f"edit_text_{pid}")],
        [InlineKeyboardButton(text="📎 Редактировать медиа", callback_data=f"edit_photo_{pid}")],
        [InlineKeyboardButton(text="🚀 Опубликовать сейчас", callback_data=f"publish_now_{pid}")],
        [InlineKeyboardButton(text="⏰ Запланировать снова", callback_data=f"replan_{pid}")],
        [InlineKeyboardButton(text="🗑 Удалить",             callback_data=f"delete_failed_{pid}")],
    ])
 
 
# ─── ФОРМАТИРОВАНИЕ ТЕКСТА ───────────────────────────────────────────────────
def format_guide() -> str:
    return (
        "✍️ <b>Напиши текст поста.</b>\n\n"
        "Используй кнопки ниже для форматирования — выдели нужный фрагмент тегами:\n\n"
        "• <b>Жирный:</b> <code>**текст**</code>\n"
        "• <i>Курсив:</i> <code>__текст__</code>\n"
        "• <u>Подчёркнутый:</u> <code>++текст++</code>\n"
        "• <s>Зачёркнутый:</s> <code>~~текст~~</code>\n"
        "• <tg-spoiler>Спойлер:</tg-spoiler> <code>||текст||</code>\n\n"
        "<b>Пример:</b>\n"
        "<code>Привет! **Это жирный** и __курсивный__ текст.</code>\n\n"
        "Или нажми кнопки ниже для подсказок 👇"
    )
 
def convert_markup(text: str) -> str:
    """Конвертирует простую разметку в HTML теги Telegram."""
    import re
    # **жирный** → <b>жирный</b>
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text, flags=re.DOTALL)
    # __курсив__ → <i>курсив</i>
    text = re.sub(r'__(.+?)__', r'<i>\1</i>', text, flags=re.DOTALL)
    # ++подчёркнутый++ → <u>подчёркнутый</u>
    text = re.sub(r'\+\+(.+?)\+\+', r'<u>\1</u>', text, flags=re.DOTALL)
    # ~~зачёркнутый~~ → <s>зачёркнутый</s>
    text = re.sub(r'~~(.+?)~~', r'<s>\1</s>', text, flags=re.DOTALL)
    # ||спойлер|| → <tg-spoiler>спойлер</tg-spoiler>
    text = re.sub(r'\|\|(.+?)\|\|', r'<tg-spoiler>\1</tg-spoiler>', text, flags=re.DOTALL)
    return text
 
 
# ─── ПУБЛИКАЦИЯ ──────────────────────────────────────────────────────────────
async def send_post_to_channel(post: dict) -> types.Message:
    """Отправить пост в канал, вернуть первое сообщение."""
    media_type = post.get("media_type", "none")
    photos     = post.get("photos", [])
    videos     = post.get("videos", [])
    music      = post.get("music")
    text       = post.get("text", "")
 
    if media_type == "photos" and photos:
        if len(photos) == 1:
            if len(text) > 1024:
                msg = await bot.send_photo(chat_id=CHANNEL_ID, photo=photos[0])
                await bot.send_message(chat_id=CHANNEL_ID, text=text, parse_mode="HTML")
            else:
                msg = await bot.send_photo(chat_id=CHANNEL_ID, photo=photos[0], caption=text, parse_mode="HTML")
        else:
            media = []
            for i, ph in enumerate(photos):
                cap = text if i == 0 and len(text) <= 1024 else ""
                media.append(InputMediaPhoto(media=ph, caption=cap, parse_mode="HTML"))
            msgs = await bot.send_media_group(chat_id=CHANNEL_ID, media=media)
            if len(text) > 1024:
                await bot.send_message(chat_id=CHANNEL_ID, text=text, parse_mode="HTML")
            msg = msgs[0]
 
    elif media_type == "videos" and videos:
        if len(videos) == 1:
            if len(text) > 1024:
                msg = await bot.send_video(chat_id=CHANNEL_ID, video=videos[0])
                await bot.send_message(chat_id=CHANNEL_ID, text=text, parse_mode="HTML")
            else:
                msg = await bot.send_video(chat_id=CHANNEL_ID, video=videos[0], caption=text, parse_mode="HTML")
        else:
            media = []
            for i, vid in enumerate(videos):
                cap = text if i == 0 and len(text) <= 1024 else ""
                media.append(InputMediaVideo(media=vid, caption=cap, parse_mode="HTML"))
            msgs = await bot.send_media_group(chat_id=CHANNEL_ID, media=media)
            if len(text) > 1024:
                await bot.send_message(chat_id=CHANNEL_ID, text=text, parse_mode="HTML")
            msg = msgs[0]
 
    elif media_type == "music" and music:
        msg = await bot.send_audio(chat_id=CHANNEL_ID, audio=music, caption=text, parse_mode="HTML")
 
    else:
        msg = await bot.send_message(chat_id=CHANNEL_ID, text=text, parse_mode="HTML")
 
    return msg
 
 
async def publish_post(post_id: int):
    global stats
    post = scheduled_posts.get(post_id)
    if not post:
        return
    try:
        msg = await send_post_to_channel(post)
        published_posts[post_id] = {
            **post,
            "message_id":   msg.message_id,
            "published_at": datetime.now(pytz.timezone(TIMEZONE)),
        }
        stats["published"] += 1
        await bot.send_message(
            chat_id=post["creator_id"],
            text=f"✅ Пост <b>#{post_id}</b> опубликован!",
            parse_mode="HTML",
            reply_markup=main_menu()
        )
        logger.info(f"Post #{post_id} published")
    except Exception as e:
        logger.error(f"Failed to publish post #{post_id}: {e}")
        stats["failed"] += 1
        failed_posts[post_id] = {
            **post,
            "error":     str(e),
            "failed_at": datetime.now(pytz.timezone(TIMEZONE)),
        }
        await bot.send_message(
            chat_id=post["creator_id"],
            text=(
                f"⚠️ <b>Ошибка публикации поста #{post_id}!</b>\n\n"
                f"❌ Причина: <code>{e}</code>\n\n"
                f"Пост сохранён в <b>«⚠️ Ошибки постов»</b>"
            ),
            parse_mode="HTML",
            reply_markup=main_menu()
        )
    finally:
        scheduled_posts.pop(post_id, None)
 
 
# ─── /start ──────────────────────────────────────────────────────────────────
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "👋 <b>Привет! Я бот для планирования постов.</b>\n\n"
        "Что умею:\n"
        "• 🖼 Посты с фото (до 10 шт), видео (до 5 шт), музыкой\n"
        "• 🎨 Форматирование: <b>жирный</b>, <i>курсив</i>, <u>подчёркнутый</u> и др.\n"
        "• 👁 Предпросмотр перед публикацией\n"
        "• ⚠️ Сохранение постов с ошибками\n"
        "• 📅 Расписание и 📊 статистика\n"
        "• ⏱ Шаблоны постов\n\n"
        "Выбери действие 👇",
        parse_mode="HTML",
        reply_markup=main_menu()
    )
 
 
# ─── СОЗДАНИЕ ПОСТА ──────────────────────────────────────────────────────────
@dp.message(F.text == "📝 Создать пост")
async def create_post_start(message: types.Message, state: FSMContext):
    await state.clear()
    uid            = message.from_user.id
    user_templates = {k: v for k, v in templates.items() if v["creator_id"] == uid}
 
    if user_templates:
        buttons = [[InlineKeyboardButton(text=f"⏱ {name}", callback_data=f"use_template_{name}")]
                   for name in user_templates]
        buttons.append([InlineKeyboardButton(text="📝 Создать с нуля", callback_data="create_from_scratch")])
        await message.answer("У тебя есть шаблоны. Использовать?",
                             reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    else:
        await ask_media_type(message, state)
 
@dp.callback_query(F.data == "create_from_scratch")
async def create_from_scratch_cb(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await ask_media_type(callback.message, state)
 
async def ask_media_type(message: types.Message, state: FSMContext):
    await state.set_state(PostForm.choosing_media_type)
    await state.update_data(photos=[], videos=[], music=None, media_type="none")
    await message.answer(
        "📎 <b>Шаг 1/3 — Медиафайлы</b>\n\nЧто добавить в пост?",
        parse_mode="HTML",
        reply_markup=media_type_keyboard()
    )
 
# Выбор типа медиа
@dp.callback_query(F.data == "media_photos", PostForm.choosing_media_type)
async def media_photos_cb(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(media_type="photos", photos=[])
    await state.set_state(PostForm.waiting_for_photos)
    await callback.message.answer(
        "🖼 <b>Отправляй фото по одному (до 10 шт)</b>\n\nКогда закончишь — нажми кнопку ниже.",
        parse_mode="HTML",
        reply_markup=more_media_keyboard(0, 10, "photos")
    )
    await callback.answer()
 
@dp.callback_query(F.data == "media_videos", PostForm.choosing_media_type)
async def media_videos_cb(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(media_type="videos", videos=[])
    await state.set_state(PostForm.waiting_for_videos)
    await callback.message.answer(
        "🎬 <b>Отправляй видео по одному (до 5 шт)</b>\n\nКогда закончишь — нажми кнопку ниже.",
        parse_mode="HTML",
        reply_markup=more_media_keyboard(0, 5, "videos")
    )
    await callback.answer()
 
@dp.callback_query(F.data == "media_music", PostForm.choosing_media_type)
async def media_music_cb(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(media_type="music")
    await state.set_state(PostForm.waiting_for_music)
    await callback.message.answer(
        "🎵 <b>Отправь аудиофайл или голосовое сообщение</b>",
        parse_mode="HTML",
        reply_markup=ReplyKeyboardRemove()
    )
    await callback.answer()
 
@dp.callback_query(F.data == "media_none", PostForm.choosing_media_type)
async def media_none_cb(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(media_type="none")
    await state.set_state(PostForm.waiting_for_text)
    await callback.message.answer(format_guide(), parse_mode="HTML",
                                  reply_markup=formatting_keyboard())
    await callback.answer()
 
# Приём фото
@dp.message(PostForm.waiting_for_photos, F.photo)
async def receive_photo(message: types.Message, state: FSMContext):
    data   = await state.get_data()
    photos = data.get("photos", [])
    if len(photos) >= 10:
        await message.answer("⚠️ Максимум 10 фото!")
        return
    photos.append(message.photo[-1].file_id)
    await state.update_data(photos=photos)
    await message.answer(
        f"✅ Фото {len(photos)} добавлено!",
        reply_markup=more_media_keyboard(len(photos), 10, "photos")
    )
 
@dp.message(PostForm.waiting_for_photos, F.text.startswith("➡️"))
async def photos_done(message: types.Message, state: FSMContext):
    data   = await state.get_data()
    photos = data.get("photos", [])
    if not photos:
        await message.answer("⚠️ Добавь хотя бы одно фото!")
        return
    await state.set_state(PostForm.waiting_for_text)
    await message.answer(
        f"✅ {len(photos)} фото добавлено!\n\n" + format_guide(),
        parse_mode="HTML",
        reply_markup=formatting_keyboard()
    )
 
# Приём видео
@dp.message(PostForm.waiting_for_videos, F.video)
async def receive_video(message: types.Message, state: FSMContext):
    data   = await state.get_data()
    videos = data.get("videos", [])
    if len(videos) >= 5:
        await message.answer("⚠️ Максимум 5 видео!")
        return
    videos.append(message.video.file_id)
    await state.update_data(videos=videos)
    await message.answer(
        f"✅ Видео {len(videos)} добавлено!",
        reply_markup=more_media_keyboard(len(videos), 5, "videos")
    )
 
@dp.message(PostForm.waiting_for_videos, F.text.startswith("➡️"))
async def videos_done(message: types.Message, state: FSMContext):
    data   = await state.get_data()
    videos = data.get("videos", [])
    if not videos:
        await message.answer("⚠️ Добавь хотя бы одно видео!")
        return
    await state.set_state(PostForm.waiting_for_text)
    await message.answer(
        f"✅ {len(videos)} видео добавлено!\n\n" + format_guide(),
        parse_mode="HTML",
        reply_markup=formatting_keyboard()
    )
 
# Приём музыки
@dp.message(PostForm.waiting_for_music, F.audio | F.voice)
async def receive_music(message: types.Message, state: FSMContext):
    music_id = message.audio.file_id if message.audio else message.voice.file_id
    await state.update_data(music=music_id)
    await state.set_state(PostForm.waiting_for_text)
    await message.answer(
        "✅ Музыка добавлена!\n\n" + format_guide(),
        parse_mode="HTML",
        reply_markup=formatting_keyboard()
    )
 
# Кнопки форматирования — подсказки
@dp.callback_query(F.data.startswith("fmt_"), PostForm.waiting_for_text)
async def fmt_hint(callback: types.CallbackQuery):
    hints = {
        "fmt_bold":      "Жирный: <code>**твой текст**</code>",
        "fmt_italic":    "Курсив: <code>__твой текст__</code>",
        "fmt_underline": "Подчёркнутый: <code>++твой текст++</code>",
        "fmt_strike":    "Зачёркнутый: <code>~~твой текст~~</code>",
        "fmt_spoiler":   "Спойлер: <code>||твой текст||</code>",
        "fmt_code":      "Код: <code>`твой текст`</code>",
    }
    hint = hints.get(callback.data, "")
    await callback.answer(hint, show_alert=True)
 
@dp.callback_query(F.data == "fmt_done", PostForm.waiting_for_text)
async def fmt_done(callback: types.CallbackQuery):
    await callback.answer("Напиши текст в чат 👇")
 
# Приём текста
@dp.message(PostForm.waiting_for_text, F.text)
async def received_text(message: types.Message, state: FSMContext):
    converted = convert_markup(message.text)
    await state.update_data(text=converted, creator_id=message.from_user.id)
    await state.set_state(PostForm.waiting_for_datetime)
    tz  = pytz.timezone(TIMEZONE)
    now = datetime.now(tz).strftime("%d.%m.%Y %H:%M")
    await message.answer(
        f"✅ Текст принят!\n\n⏰ <b>Шаг 3/3 — Время публикации</b>\n\n"
        f"Сейчас: <code>{now}</code>\nФормат: <code>ДД.ММ.ГГГГ ЧЧ:ММ</code>",
        parse_mode="HTML",
        reply_markup=ReplyKeyboardRemove()
    )
 
@dp.message(PostForm.waiting_for_datetime, F.text)
async def received_datetime(message: types.Message, state: FSMContext):
    try:
        tz         = pytz.timezone(TIMEZONE)
        publish_dt = tz.localize(datetime.strptime(message.text.strip(), "%d.%m.%Y %H:%M"))
        if publish_dt <= datetime.now(tz):
            await message.answer("⚠️ Это время уже прошло!")
            return
        await state.update_data(publish_at=publish_dt.isoformat())
        await state.set_state(PostForm.waiting_for_confirm)
        data       = await state.get_data()
        media_type = data.get("media_type", "none")
        media_info = {
            "photos": f"🖼 Фото: {len(data.get('photos', []))} шт",
            "videos": f"🎬 Видео: {len(data.get('videos', []))} шт",
            "music":  "🎵 Музыка: прикреплена",
            "none":   "📝 Без медиа",
        }.get(media_type, "📝 Без медиа")
 
        await message.answer(
            f"📋 <b>Пост готов:</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"{media_info}\n"
            f"⏰ <code>{publish_dt.strftime('%d.%m.%Y в %H:%M')}</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Нажми <b>«👁 Предпросмотр»</b> чтобы проверить пост.",
            parse_mode="HTML",
            reply_markup=confirm_keyboard()
        )
    except ValueError:
        await message.answer("❌ Неверный формат! Пример: <code>25.12.2025 18:30</code>", parse_mode="HTML")
 
 
# ─── ПРЕДПРОСМОТР ────────────────────────────────────────────────────────────
async def send_preview(message: types.Message, data: dict):
    media_type = data.get("media_type", "none")
    photos     = data.get("photos", [])
    videos     = data.get("videos", [])
    music      = data.get("music")
    text       = data.get("text", "")
 
    await message.answer("👁 <b>Так будет выглядеть пост в канале:</b>", parse_mode="HTML")
 
    if media_type == "photos" and photos:
        if len(photos) == 1:
            cap = text if len(text) <= 1024 else ""
            await message.answer_photo(photo=photos[0], caption=cap, parse_mode="HTML")
            if len(text) > 1024:
                await message.answer(text, parse_mode="HTML")
        else:
            media = []
            for i, ph in enumerate(photos):
                cap = text if i == 0 and len(text) <= 1024 else ""
                media.append(InputMediaPhoto(media=ph, caption=cap, parse_mode="HTML"))
            await message.answer_media_group(media=media)
            if len(text) > 1024:
                await message.answer(text, parse_mode="HTML")
 
    elif media_type == "videos" and videos:
        if len(videos) == 1:
            cap = text if len(text) <= 1024 else ""
            await message.answer_video(video=videos[0], caption=cap, parse_mode="HTML")
            if len(text) > 1024:
                await message.answer(text, parse_mode="HTML")
        else:
            media = []
            for i, vid in enumerate(videos):
                cap = text if i == 0 and len(text) <= 1024 else ""
                media.append(InputMediaVideo(media=vid, caption=cap, parse_mode="HTML"))
            await message.answer_media_group(media=media)
            if len(text) > 1024:
                await message.answer(text, parse_mode="HTML")
 
    elif media_type == "music" and music:
        await message.answer_audio(audio=music, caption=text, parse_mode="HTML")
 
    else:
        await message.answer(text, parse_mode="HTML")
 
@dp.callback_query(F.data == "preview_post", PostForm.waiting_for_confirm)
async def preview_new_post(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await callback.answer()
    await send_preview(callback.message, data)
    await callback.message.answer("Подтверди или измени:", reply_markup=confirm_keyboard())
 
@dp.callback_query(F.data.startswith("preview_"))
async def preview_existing(callback: types.CallbackQuery):
    try:
        pid  = int(callback.data.split("_")[1])
    except Exception:
        await callback.answer()
        return
    post = scheduled_posts.get(pid) or published_posts.get(pid) or failed_posts.get(pid)
    if not post:
        await callback.answer("Пост не найден.")
        return
    await callback.answer()
    await send_preview(callback.message, post)
 
 
# ─── РЕДАКТИРОВАНИЕ ЧЕРНОВИКА ────────────────────────────────────────────────
@dp.callback_query(F.data == "edit_draft_text")
async def edit_draft_text_cb(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(DraftEdit.editing_text)
    await callback.message.answer(
        "✍️ <b>Введи новый текст:</b>\n\n" + format_guide(),
        parse_mode="HTML",
        reply_markup=formatting_keyboard()
    )
    await callback.answer()
 
@dp.message(DraftEdit.editing_text, F.text)
async def edit_draft_text_save(message: types.Message, state: FSMContext):
    converted = convert_markup(message.text)
    await state.update_data(text=converted)
    await state.set_state(PostForm.waiting_for_confirm)
    await message.answer("✅ Текст обновлён!", reply_markup=confirm_keyboard())
 
@dp.callback_query(F.data == "edit_draft_media")
async def edit_draft_media_cb(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(photos=[], videos=[], music=None)
    await state.set_state(PostForm.choosing_media_type)
    await callback.message.answer(
        "📎 Выбери новый тип медиа:",
        reply_markup=media_type_keyboard()
    )
    await callback.answer()
 
@dp.callback_query(F.data == "edit_draft_time")
async def edit_draft_time_cb(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(DraftEdit.editing_datetime)
    tz  = pytz.timezone(TIMEZONE)
    now = datetime.now(tz).strftime("%d.%m.%Y %H:%M")
    await callback.message.answer(
        f"⏰ <b>Новое время:</b>\n\nСейчас: <code>{now}</code>\nФормат: <code>ДД.ММ.ГГГГ ЧЧ:ММ</code>",
        parse_mode="HTML"
    )
    await callback.answer()
 
@dp.message(DraftEdit.editing_datetime, F.text)
async def edit_draft_time_save(message: types.Message, state: FSMContext):
    try:
        tz         = pytz.timezone(TIMEZONE)
        publish_dt = tz.localize(datetime.strptime(message.text.strip(), "%d.%m.%Y %H:%M"))
        if publish_dt <= datetime.now(tz):
            await message.answer("⚠️ Время уже прошло!")
            return
        await state.update_data(publish_at=publish_dt.isoformat())
        await state.set_state(PostForm.waiting_for_confirm)
        await message.answer(
            f"✅ Время обновлено!\n📅 <code>{publish_dt.strftime('%d.%m.%Y в %H:%M')}</code>",
            parse_mode="HTML",
            reply_markup=confirm_keyboard()
        )
    except ValueError:
        await message.answer("❌ Неверный формат! Пример: <code>25.12.2025 18:30</code>", parse_mode="HTML")
 
 
# ─── ШАБЛОНЫ ─────────────────────────────────────────────────────────────────
@dp.callback_query(F.data == "save_template", PostForm.waiting_for_confirm)
async def save_template_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(TemplateForm.waiting_name)
    await callback.message.answer("💾 Введи название шаблона:")
    await callback.answer()
 
@dp.message(TemplateForm.waiting_name, F.text)
async def save_template_finish(message: types.Message, state: FSMContext):
    data = await state.get_data()
    name = message.text.strip()
    templates[name] = {
        "media_type": data.get("media_type", "none"),
        "photos":     data.get("photos", []),
        "videos":     data.get("videos", []),
        "music":      data.get("music"),
        "text":       data.get("text", ""),
        "creator_id": message.from_user.id,
    }
    await state.set_state(PostForm.waiting_for_confirm)
    await message.answer(
        f"✅ Шаблон <b>{name}</b> сохранён!",
        parse_mode="HTML",
        reply_markup=confirm_keyboard()
    )
 
@dp.callback_query(F.data.startswith("use_template_"))
async def use_template(callback: types.CallbackQuery, state: FSMContext):
    name = callback.data.replace("use_template_", "")
    tmpl = templates.get(name)
    if not tmpl:
        await callback.answer("Шаблон не найден.")
        return
    await state.update_data(
        media_type=tmpl.get("media_type", "none"),
        photos=tmpl.get("photos", []),
        videos=tmpl.get("videos", []),
        music=tmpl.get("music"),
        text=tmpl.get("text", ""),
        creator_id=callback.from_user.id
    )
    await state.set_state(PostForm.waiting_for_datetime)
    tz  = pytz.timezone(TIMEZONE)
    now = datetime.now(tz).strftime("%d.%m.%Y %H:%M")
    await callback.message.answer(
        f"✅ Шаблон <b>{name}</b> загружен!\n\n"
        f"⏰ Укажи время публикации:\n\nСейчас: <code>{now}</code>\nФормат: <code>ДД.ММ.ГГГГ ЧЧ:ММ</code>",
        parse_mode="HTML",
        reply_markup=ReplyKeyboardRemove()
    )
    await callback.answer()
 
@dp.message(F.text == "⏱ Шаблоны")
async def show_templates(message: types.Message):
    uid            = message.from_user.id
    user_templates = {k: v for k, v in templates.items() if v["creator_id"] == uid}
    if not user_templates:
        await message.answer(
            "📭 Нет шаблонов.\n\nСоздай пост и нажми <b>«💾 Шаблон»</b>",
            parse_mode="HTML", reply_markup=main_menu()
        )
        return
    buttons = []
    for name in user_templates:
        buttons.append([
            InlineKeyboardButton(text=f"⏱ {name}", callback_data=f"use_template_{name}"),
            InlineKeyboardButton(text="🗑",          callback_data=f"del_template_{name}"),
        ])
    await message.answer("⏱ <b>Шаблоны:</b>", parse_mode="HTML",
                         reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
 
@dp.callback_query(F.data.startswith("del_template_"))
async def delete_template(callback: types.CallbackQuery):
    name = callback.data.replace("del_template_", "")
    templates.pop(name, None)
    await callback.message.edit_text(f"🗑 Шаблон <b>{name}</b> удалён.", parse_mode="HTML")
    await callback.answer()
 
 
# ─── ПОДТВЕРЖДЕНИЕ ───────────────────────────────────────────────────────────
@dp.callback_query(F.data == "confirm_post", PostForm.waiting_for_confirm)
async def confirm_post(callback: types.CallbackQuery, state: FSMContext):
    global post_counter
    data = await state.get_data()
    await state.clear()
    post_counter += 1
    pid        = post_counter
    publish_dt = datetime.fromisoformat(data["publish_at"])
    scheduled_posts[pid] = {
        "media_type": data.get("media_type", "none"),
        "photos":     data.get("photos", []),
        "videos":     data.get("videos", []),
        "music":      data.get("music"),
        "photo":      data.get("photos", [None])[0],
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
 
 
# ─── МОИ ПОСТЫ ───────────────────────────────────────────────────────────────
@dp.message(F.text == "📋 Мои посты")
async def list_posts(message: types.Message):
    uid        = message.from_user.id
    user_posts = {pid: p for pid, p in scheduled_posts.items() if p["creator_id"] == uid}
    if not user_posts:
        await message.answer("📭 Нет запланированных постов.", reply_markup=main_menu())
        return
    text = "📋 <b>Запланированные посты:</b>\n\n"
    for pid, post in sorted(user_posts.items(), key=lambda x: x[1]["publish_at"]):
        dt      = post["publish_at"].strftime("%d.%m.%Y в %H:%M")
        mt      = {"photos": "🖼", "videos": "🎬", "music": "🎵", "none": "📝"}.get(post.get("media_type", "none"), "📝")
        preview = (post["text"][:50] + "...") if len(post["text"]) > 50 else post["text"]
        text   += f"{mt} <b>#{pid}</b> — ⏰ {dt}\n💬 {preview}\n\n"
    await message.answer(text, parse_mode="HTML", reply_markup=main_menu())
 
 
# ─── ОПУБЛИКОВАННЫЕ ──────────────────────────────────────────────────────────
@dp.message(F.text == "📰 Опубликованные")
async def list_published(message: types.Message):
    uid        = message.from_user.id
    user_posts = {pid: p for pid, p in published_posts.items() if p["creator_id"] == uid}
    if not user_posts:
        await message.answer("📭 Нет опубликованных постов.", reply_markup=main_menu())
        return
    text = "📰 <b>Опубликованные посты:</b>\n\n"
    for pid, post in sorted(user_posts.items(), key=lambda x: x[1]["published_at"], reverse=True):
        dt      = post["published_at"].strftime("%d.%m.%Y в %H:%M")
        mt      = {"photos": "🖼", "videos": "🎬", "music": "🎵", "none": "📝"}.get(post.get("media_type", "none"), "📝")
        preview = (post["text"][:50] + "...") if len(post["text"]) > 50 else post["text"]
        text   += f"{mt} <b>#{pid}</b> — 📅 {dt}\n💬 {preview}\n\n"
    await message.answer(text, parse_mode="HTML", reply_markup=main_menu())
 
 
# ─── ОШИБКИ ПОСТОВ ───────────────────────────────────────────────────────────
@dp.message(F.text == "⚠️ Ошибки постов")
async def list_failed(message: types.Message):
    uid        = message.from_user.id
    user_posts = {pid: p for pid, p in failed_posts.items() if p["creator_id"] == uid}
    if not user_posts:
        await message.answer("✅ Постов с ошибками нет!", reply_markup=main_menu())
        return
    await message.answer(f"⚠️ <b>Постов с ошибками: {len(user_posts)}</b>", parse_mode="HTML")
    for pid, post in user_posts.items():
        dt      = post["failed_at"].strftime("%d.%m.%Y в %H:%M")
        error   = post.get("error", "Неизвестная ошибка")
        preview = (post["text"][:60] + "...") if len(post["text"]) > 60 else post["text"]
        await message.answer(
            f"⚠️ <b>Пост #{pid}</b>\n"
            f"🕐 {dt}\n❌ <code>{error}</code>\n💬 {preview}",
            parse_mode="HTML",
            reply_markup=failed_post_keyboard(pid)
        )
 
@dp.callback_query(F.data.startswith("publish_now_"))
async def publish_now(callback: types.CallbackQuery):
    global stats
    pid  = int(callback.data.split("_")[2])
    post = failed_posts.get(pid)
    if not post:
        await callback.answer("Пост не найден.")
        return
    await callback.answer()
    msg = await callback.message.answer("🚀 Публикую...")
    try:
        sent = await send_post_to_channel(post)
        published_posts[pid] = {**post, "message_id": sent.message_id, "published_at": datetime.now(pytz.timezone(TIMEZONE))}
        failed_posts.pop(pid, None)
        stats["published"] += 1
        await msg.edit_text(f"✅ Пост <b>#{pid}</b> опубликован!", parse_mode="HTML")
        await callback.message.answer("Что дальше?", reply_markup=main_menu())
    except Exception as e:
        await msg.edit_text(f"⚠️ Снова ошибка: <code>{e}</code>", parse_mode="HTML")
 
@dp.callback_query(F.data.startswith("delete_failed_"))
async def delete_failed(callback: types.CallbackQuery):
    pid = int(callback.data.split("_")[2])
    failed_posts.pop(pid, None)
    await callback.message.edit_text(f"🗑 Пост <b>#{pid}</b> удалён.", parse_mode="HTML")
    await callback.answer()
 
 
# ─── РАСПИСАНИЕ ──────────────────────────────────────────────────────────────
@dp.message(F.text == "📅 Расписание")
async def show_schedule(message: types.Message):
    uid        = message.from_user.id
    user_posts = {pid: p for pid, p in scheduled_posts.items() if p["creator_id"] == uid}
    if not user_posts:
        await message.answer("📭 Нет запланированных постов.", reply_markup=main_menu())
        return
    tz           = pytz.timezone(TIMEZONE)
    now          = datetime.now(tz)
    sorted_p     = sorted(user_posts.items(), key=lambda x: x[1]["publish_at"])
    text         = "📅 <b>Расписание постов:</b>\n\n"
    current_date = None
    weekdays     = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    for pid, post in sorted_p:
        dt   = post["publish_at"]
        date = dt.strftime("%d.%m.%Y")
        if date != current_date:
            current_date = date
            wd    = weekdays[dt.weekday()]
            today = "🔵 Сегодня" if dt.date() == now.date() else f"📆 {wd}, {date}"
            text += f"\n{today}\n"
        mt      = {"photos": "🖼", "videos": "🎬", "music": "🎵", "none": "📝"}.get(post.get("media_type", "none"), "📝")
        preview = (post["text"][:30] + "...") if len(post["text"]) > 30 else post["text"]
        text   += f"  ⏰ {dt.strftime('%H:%M')} {mt} <b>#{pid}</b> — {preview}\n"
    await message.answer(text, parse_mode="HTML", reply_markup=main_menu())
 
 
# ─── СТАТИСТИКА ──────────────────────────────────────────────────────────────
@dp.message(F.text == "📊 Статистика")
async def show_stats(message: types.Message):
    uid       = message.from_user.id
    scheduled = len([p for p in scheduled_posts.values() if p["creator_id"] == uid])
    published = len([p for p in published_posts.values() if p["creator_id"] == uid])
    failed    = len([p for p in failed_posts.values()    if p["creator_id"] == uid])
    tmpl      = len([t for t in templates.values()       if t["creator_id"] == uid])
    total     = published + failed
    rate      = round(published / total * 100) if total > 0 else 0
    await message.answer(
        f"📊 <b>Статистика:</b>\n\n"
        f"📋 Запланировано: <b>{scheduled}</b>\n"
        f"✅ Опубликовано: <b>{published}</b>\n"
        f"⚠️ Ошибок: <b>{failed}</b>\n"
        f"⏱ Шаблонов: <b>{tmpl}</b>\n\n"
        f"📈 Успешность: <b>{rate}%</b>\n\n"
        f"{'🎉 Отлично!' if rate >= 90 else '💪 Есть куда расти!'}",
        parse_mode="HTML", reply_markup=main_menu()
    )
 
 
# ─── ОТМЕНА ПОСТА ────────────────────────────────────────────────────────────
@dp.message(F.text == "❌ Отменить пост")
async def cancel_post_menu(message: types.Message):
    uid        = message.from_user.id
    user_posts = {pid: p for pid, p in scheduled_posts.items() if p["creator_id"] == uid}
    if not user_posts:
        await message.answer("📭 Нет постов для отмены.", reply_markup=main_menu())
        return
    buttons = [[InlineKeyboardButton(
        text=f"❌ #{pid} — {p['publish_at'].strftime('%d.%m %H:%M')}",
        callback_data=f"delete_{pid}"
    )] for pid, p in user_posts.items()]
    await message.answer("Выбери пост:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
 
@dp.callback_query(F.data.startswith("delete_"))
async def delete_post(callback: types.CallbackQuery):
    global stats
    parts = callback.data.split("_")
    if callback.data.startswith("delete_failed_"):
        await callback.answer()
        return
    pid = int(parts[1])
    if pid in scheduled_posts and scheduled_posts[pid]["creator_id"] == callback.from_user.id:
        try:
            scheduler.remove_job(f"post_{pid}")
        except Exception:
            pass
        scheduled_posts.pop(pid, None)
        stats["cancelled"] += 1
        await callback.message.edit_text(f"✅ Пост <b>#{pid}</b> отменён.", parse_mode="HTML")
    else:
        await callback.message.edit_text("⚠️ Пост не найден.")
    await callback.answer()
 
 
# ─── РЕДАКТИРОВАНИЕ ──────────────────────────────────────────────────────────
@dp.message(F.text == "✏️ Редактировать")
async def edit_menu(message: types.Message):
    uid        = message.from_user.id
    user_sched = {pid: p for pid, p in scheduled_posts.items() if p["creator_id"] == uid}
    user_pub   = {pid: p for pid, p in published_posts.items()  if p["creator_id"] == uid}
    user_fail  = {pid: p for pid, p in failed_posts.items()     if p["creator_id"] == uid}
    if not user_sched and not user_pub and not user_fail:
        await message.answer("📭 Нет постов для редактирования.", reply_markup=main_menu())
        return
    buttons = []
    if user_sched:
        buttons.append([InlineKeyboardButton(text="─── 📋 Запланированные ───", callback_data="noop")])
        for pid, p in user_sched.items():
            buttons.append([InlineKeyboardButton(
                text=f"✏️ #{pid} — ⏰ {p['publish_at'].strftime('%d.%m %H:%M')}",
                callback_data=f"editsel_{pid}_0"
            )])
    if user_pub:
        buttons.append([InlineKeyboardButton(text="─── 📰 Опубликованные ───", callback_data="noop")])
        for pid, p in user_pub.items():
            buttons.append([InlineKeyboardButton(
                text=f"✏️ #{pid} — 📅 {p['published_at'].strftime('%d.%m %H:%M')}",
                callback_data=f"editsel_{pid}_1"
            )])
    if user_fail:
        buttons.append([InlineKeyboardButton(text="─── ⚠️ С ошибками ───", callback_data="noop")])
        for pid, p in user_fail.items():
            buttons.append([InlineKeyboardButton(
                text=f"✏️ #{pid} — ⚠️ ошибка",
                callback_data=f"editsel_{pid}_2"
            )])
    await message.answer("Выбери пост:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
 
@dp.callback_query(F.data == "noop")
async def noop(callback: types.CallbackQuery):
    await callback.answer()
 
@dp.callback_query(F.data.startswith("editsel_"))
async def edit_select(callback: types.CallbackQuery, state: FSMContext):
    parts  = callback.data.split("_")
    pid    = int(parts[1])
    ptype  = parts[2]
    is_pub = ptype == "1"
    post   = published_posts.get(pid) if is_pub else (failed_posts.get(pid) if ptype == "2" else scheduled_posts.get(pid))
    if not post:
        await callback.answer("Пост не найден.")
        return
    await state.update_data(editing_pid=pid, is_published=is_pub, is_failed=ptype == "2")
    await state.set_state(EditForm.choosing_field)
    preview = (post["text"][:60] + "...") if len(post["text"]) > 60 else post["text"]
    mt      = {"photos": "🖼", "videos": "🎬", "music": "🎵", "none": "📝"}.get(post.get("media_type", "none"), "📝")
    await callback.message.edit_text(
        f"✏️ <b>Пост #{pid}</b>\n{mt} {preview}\n\nЧто изменить?",
        parse_mode="HTML",
        reply_markup=edit_field_keyboard(pid, is_pub)
    )
    await callback.answer()
 
@dp.callback_query(F.data.startswith("edit_text_"))
async def edit_text_start(callback: types.CallbackQuery, state: FSMContext):
    pid = int(callback.data.split("_")[2])
    await state.update_data(editing_pid=pid)
    await state.set_state(EditForm.editing_text)
    await callback.message.answer(
        "✍️ <b>Новый текст:</b>\n\n" + format_guide(),
        parse_mode="HTML",
        reply_markup=formatting_keyboard()
    )
    await callback.answer()
 
@dp.message(EditForm.editing_text, F.text)
async def edit_text_save(message: types.Message, state: FSMContext):
    data      = await state.get_data()
    pid       = data["editing_pid"]
    is_pub    = data.get("is_published", False)
    is_fail   = data.get("is_failed", False)
    new_text  = convert_markup(message.text)
 
    if is_pub and pid in published_posts:
        published_posts[pid]["text"] = new_text
        post = published_posts[pid]
        try:
            if post.get("media_type") in ("photos", "videos") and len(new_text) <= 1024:
                await bot.edit_message_caption(chat_id=CHANNEL_ID, message_id=post["message_id"], caption=new_text, parse_mode="HTML")
            elif post.get("media_type") == "none":
                await bot.edit_message_text(chat_id=CHANNEL_ID, message_id=post["message_id"], text=new_text, parse_mode="HTML")
            await message.answer(f"✅ Текст поста <b>#{pid}</b> обновлён в канале!", parse_mode="HTML", reply_markup=main_menu())
        except Exception as e:
            await message.answer(f"⚠️ Ошибка: {e}", reply_markup=main_menu())
    elif is_fail and pid in failed_posts:
        failed_posts[pid]["text"] = new_text
        await message.answer(f"✅ Текст обновлён! Теперь публикуй через «⚠️ Ошибки постов»", reply_markup=main_menu())
    elif pid in scheduled_posts:
        scheduled_posts[pid]["text"] = new_text
        await message.answer(f"✅ Текст поста <b>#{pid}</b> обновлён!", parse_mode="HTML", reply_markup=main_menu())
    else:
        await message.answer("⚠️ Пост не найден.", reply_markup=main_menu())
    await state.clear()
 
@dp.callback_query(F.data.startswith("edit_photo_"))
async def edit_media_start(callback: types.CallbackQuery, state: FSMContext):
    pid = int(callback.data.split("_")[2])
    await state.update_data(editing_pid=pid)
    await state.set_state(EditForm.editing_media)
    await callback.message.answer(
        "📎 Выбери новый тип медиа:",
        reply_markup=media_type_keyboard()
    )
    await callback.answer()
 
@dp.callback_query(F.data.startswith("edit_time_"))
async def edit_time_start(callback: types.CallbackQuery, state: FSMContext):
    pid = int(callback.data.split("_")[2])
    await state.update_data(editing_pid=pid)
    await state.set_state(EditForm.editing_datetime)
    tz  = pytz.timezone(TIMEZONE)
    now = datetime.now(tz).strftime("%d.%m.%Y %H:%M")
    await callback.message.answer(
        f"⏰ <b>Новое время:</b>\n\nСейчас: <code>{now}</code>\nФормат: <code>ДД.ММ.ГГГГ ЧЧ:ММ</code>",
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
            await message.answer("⚠️ Время уже прошло!")
            return
        if pid in scheduled_posts:
            scheduled_posts[pid]["publish_at"] = publish_dt
            try:
                scheduler.remove_job(f"post_{pid}")
            except Exception:
                pass
            scheduler.add_job(publish_post, trigger=DateTrigger(run_date=publish_dt), args=[pid], id=f"post_{pid}")
            await message.answer(
                f"✅ Время обновлено!\n📅 <code>{publish_dt.strftime('%d.%m.%Y в %H:%M')}</code>",
                parse_mode="HTML", reply_markup=main_menu()
            )
        else:
            await message.answer("⚠️ Пост не найден.", reply_markup=main_menu())
    except ValueError:
        await message.answer("❌ Неверный формат! Пример: <code>25.12.2025 18:30</code>", parse_mode="HTML")
        return
    await state.clear()
 
 
# ─── ПЕРЕПЛАНИРОВАТЬ ─────────────────────────────────────────────────────────
@dp.callback_query(F.data.startswith("replan_"))
async def replan_post(callback: types.CallbackQuery, state: FSMContext):
    pid  = int(callback.data.split("_")[1])
    post = failed_posts.get(pid) or scheduled_posts.get(pid)
    if not post:
        await callback.answer("Пост не найден.")
        return
    await state.update_data(replan_pid=pid)
    await state.set_state(RepeatForm.waiting_datetime)
    tz  = pytz.timezone(TIMEZONE)
    now = datetime.now(tz).strftime("%d.%m.%Y %H:%M")
    await callback.message.answer(
        f"🔁 <b>Новое время для поста #{pid}:</b>\n\nСейчас: <code>{now}</code>\nФормат: <code>ДД.ММ.ГГГГ ЧЧ:ММ</code>",
        parse_mode="HTML"
    )
    await callback.answer()
 
@dp.message(RepeatForm.waiting_datetime, F.text)
async def replan_datetime(message: types.Message, state: FSMContext):
    global post_counter
    data = await state.get_data()
    pid  = data["replan_pid"]
    post = failed_posts.get(pid) or scheduled_posts.get(pid)
    try:
        tz         = pytz.timezone(TIMEZONE)
        publish_dt = tz.localize(datetime.strptime(message.text.strip(), "%d.%m.%Y %H:%M"))
        if publish_dt <= datetime.now(tz):
            await message.answer("⚠️ Время уже прошло!")
            return
        if pid in failed_posts:
            failed_posts.pop(pid)
        scheduled_posts[pid] = {**post, "publish_at": publish_dt}
        try:
            scheduler.remove_job(f"post_{pid}")
        except Exception:
            pass
        scheduler.add_job(publish_post, trigger=DateTrigger(run_date=publish_dt), args=[pid], id=f"post_{pid}")
        await message.answer(
            f"✅ Пост <b>#{pid}</b> запланирован!\n📅 <code>{publish_dt.strftime('%d.%m.%Y в %H:%M')}</code>",
            parse_mode="HTML", reply_markup=main_menu()
        )
        await state.clear()
    except ValueError:
        await message.answer("❌ Неверный формат! Пример: <code>25.12.2025 18:30</code>", parse_mode="HTML")
 
 
# ─── ЗАПУСК ──────────────────────────────────────────────────────────────────
async def main():
    scheduler.start()
    logger.info("Bot started. Scheduler running.")
    await dp.start_polling(bot)
 
if __name__ == "__main__":
    asyncio.run(main())
