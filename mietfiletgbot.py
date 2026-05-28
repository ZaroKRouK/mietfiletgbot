import json
import logging
import os
import asyncio
import tempfile
from datetime import datetime
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, FSInputFile, CallbackQuery
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command

from config import BOT_TOKEN, API_BASE_URL, CLIENT_USERNAME, CLIENT_PASSWORD, USERS_FILE, FILES_FILE, TEMP_DIR
from api_client import FileServerClient

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[logging.FileHandler("bot_logs.txt", encoding="utf-8"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Глобальные хранилища
users_db = {}       # { tg_id: {"server_username": str, "server_password": str, "full_name": str, ...} }
files_meta = {}     # { fid: {"original_name": str, "uploader_id": int, "file_size": int, "upload_time": str} }
next_file_id = 1    # не используется, fid генерируется сервером

# Клиент для API от имени CLIENT (для создания USER)
client_api = FileServerClient(API_BASE_URL, CLIENT_USERNAME, CLIENT_PASSWORD)


# ========== Работа с локальными JSON ==========
def load_users():
    global users_db
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, "r", encoding="utf-8") as f:
                users_db = json.load(f)
                # преобразуем ключи из строк в int
                users_db = {int(k): v for k, v in users_db.items()}
        except Exception as e:
            logger.error(f"Ошибка загрузки {USERS_FILE}: {e}")
            users_db = {}
    else:
        users_db = {}


def save_users():
    try:
        with open(USERS_FILE, "w", encoding="utf-8") as f:
            json.dump(users_db, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Ошибка сохранения {USERS_FILE}: {e}")


def load_files():
    global files_meta
    if os.path.exists(FILES_FILE):
        try:
            with open(FILES_FILE, "r", encoding="utf-8") as f:
                files_meta = json.load(f)
        except Exception as e:
            logger.error(f"Ошибка загрузки {FILES_FILE}: {e}")
            files_meta = {}
    else:
        files_meta = {}


def save_files():
    try:
        with open(FILES_FILE, "w", encoding="utf-8") as f:
            json.dump(files_meta, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Ошибка сохранения {FILES_FILE}: {e}")


# ========== Вспомогательные функции ==========
async def ensure_user_registered(tg_id: int, tg_username: str = None, full_name: str = None) -> FileServerClient:
    """
    Проверяет, зарегистрирован ли пользователь на сервере.
    Если нет – создаёт USER через CLIENT API и сохраняет учётные данные.
    Возвращает клиент API, авторизованный под этим USER.
    """
    if tg_id in users_db:
        # уже есть учётные данные
        creds = users_db[tg_id]
        return FileServerClient(API_BASE_URL, creds["server_username"], creds["server_password"])

    # Создаём нового USER на сервере
    # Используем username = tg_{id} или tg_username, если он есть
    server_username = f"tg_{tg_id}" if not tg_username else f"tg_{tg_username}"
    # но username на сервере должен быть уникальным, добавим суффикс
    server_username = f"{server_username}_{tg_id}"  # гарантия уникальности

    try:
        user_name, user_pass = await client_api.create_user(server_username)
        logger.info(f"Создан USER на сервере: {user_name} для tg_id {tg_id}")
    except Exception as e:
        logger.error(f"Ошибка создания USER: {e}")
        raise Exception("Не удалось зарегистрировать вас на сервере. Попробуйте позже.")

    # Сохраняем в локальную БД
    users_db[tg_id] = {
        "server_username": user_name,
        "server_password": user_pass,
        "tg_username": tg_username,
        "full_name": full_name,
        "first_login": datetime.now().isoformat(),
        "last_login": datetime.now().isoformat(),
        "login_count": 1
    }
    save_users()

    return FileServerClient(API_BASE_URL, user_name, user_pass)


def get_user_client(tg_id: int) -> FileServerClient:
    """Возвращает API-клиент для уже зарегистрированного пользователя"""
    if tg_id not in users_db:
        raise ValueError("Пользователь не зарегистрирован")
    creds = users_db[tg_id]
    return FileServerClient(API_BASE_URL, creds["server_username"], creds["server_password"])


# ========== Обработчики команд ==========
@dp.message(Command("start"))
async def cmd_start(message: Message):
    tg_id = message.from_user.id
    try:
        await ensure_user_registered(tg_id, message.from_user.username, message.from_user.full_name)
        await message.answer(
            f"Привет, {message.from_user.full_name}!\n\n"
            f"Я работаю с файловым сервером. Отправь мне любой документ – он загрузится в твоё личное облако.\n"
            f"Команды: /help, /files, /myfiles, /get <ID>"
        )
    except Exception as e:
        logger.exception("Ошибка регистрации")
        await message.answer("❌ Ошибка регистрации. Попробуйте позже.")


@dp.message(Command("help"))
async def cmd_help(message: Message):
    text = (
        "<b>📋 Доступные команды:</b>\n\n"
        "• /start – регистрация\n"
        "• /help – это сообщение\n"
        "• /files – список всех файлов (из локального кэша)\n"
        "• /myfiles – только твои файлы\n"
        "• /get <ID> – получить файл по идентификатору (если чужой – запросишь разрешение)\n\n"
        "<b>Как загрузить файл:</b>\n"
        "Просто отправь файл в чат – он загрузится на сервер и ты получишь его ID."
    )
    await message.answer(text, parse_mode="HTML")


@dp.message(F.document)
async def handle_document(message: Message):
    tg_id = message.from_user.id
    # Регистрируем пользователя, если он новый
    try:
        user_api = await ensure_user_registered(tg_id, message.from_user.username, message.from_user.full_name)
    except Exception as e:
        await message.answer("❌ Сначала зарегистрируйтесь через /start")
        return

    document = message.document
    original_name = document.file_name or f"file_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    # Скачиваем файл от Telegram
    file_info = await bot.get_file(document.file_id)
    file_bytes = await bot.download_file(file_info.file_path)
    file_data = file_bytes.read()  # bytes

    # Загружаем на сервер
    try:
        fid = await user_api.upload_file(file_data, original_name)
        logger.info(f"Пользователь {tg_id} загрузил файл {original_name}, fid={fid}")
    except Exception as e:
        logger.exception("Ошибка загрузки на сервер")
        await message.answer(f"❌ Ошибка загрузки файла: {e}")
        return

    # Сохраняем метаданные локально
    files_meta[fid] = {
        "original_name": original_name,
        "uploader_id": tg_id,
        "file_size": document.file_size,
        "upload_time": datetime.now().isoformat()
    }
    save_files()

    await message.answer(
        f"✅ Файл <b>{original_name}</b> загружен на сервер!\n"
        f"Его ID: <code>{fid}</code>\n"
        f"Вы можете поделиться этим ID с другими.",
        parse_mode="HTML"
    )


@dp.message(Command("files"))
async def cmd_files(message: Message):
    if not files_meta:
        await message.answer("📂 Пока нет загруженных файлов.")
        return

    text = "<b>Все файлы в системе:</b>\n\n"
    for fid, meta in sorted(files_meta.items(), key=lambda x: x[1]["upload_time"], reverse=True):
        owner_id = meta["uploader_id"]
        owner_name = users_db.get(owner_id, {}).get("full_name", f"User {owner_id}")
        size_mb = meta["file_size"] / (1024 * 1024)
        text += f"🔹 <b>ID {fid}</b> – {meta['original_name']}\n   └─ Владелец: {owner_name}\n   └─ {size_mb:.2f} МБ\n\n"

    if len(text) > 4000:
        text = text[:3900] + "\n..."
    await message.answer(text, parse_mode="HTML")


@dp.message(Command("myfiles"))
async def cmd_myfiles(message: Message):
    tg_id = message.from_user.id
    my_files = {fid: meta for fid, meta in files_meta.items() if meta["uploader_id"] == tg_id}
    if not my_files:
        await message.answer("У тебя пока нет загруженных файлов.")
        return

    text = f"<b>Твои файлы ({len(my_files)} шт.):</b>\n\n"
    for fid, meta in sorted(my_files.items(), key=lambda x: x[1]["upload_time"], reverse=True):
        size_mb = meta["file_size"] / (1024 * 1024)
        text += (
            f"🔹 <b>ID {fid}</b> – {meta['original_name']}\n"
            f"   └─ Размер: {size_mb:.2f} МБ\n"
            f"   └─ Загружен: {meta['upload_time'][:10]}\n\n"
        )
    await message.answer(text, parse_mode="HTML")


@dp.message(Command("get"))
async def cmd_get(message: Message):
    parts = message.text.strip().split()
    if len(parts) != 2:
        await message.answer("❌ Использование: /get <ID>")
        return

    fid = parts[1]
    if fid not in files_meta:
        await message.answer("❌ Файл с таким ID не найден в локальном кэше.")
        return

    meta = files_meta[fid]
    requester_id = message.from_user.id
    owner_id = meta["uploader_id"]

    # Если запрашивающий – владелец
    if requester_id == owner_id:
        # Скачиваем файл с сервера под своими учётными данными
        try:
            user_api = get_user_client(requester_id)
            file_bytes = await user_api.download_file(fid)
        except Exception as e:
            logger.exception("Ошибка скачивания")
            await message.answer(f"❌ Не удалось скачать файл: {e}")
            return

        # Сохраняем во временный файл и отправляем
        with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{meta['original_name']}") as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name
        try:
            await message.answer_document(
                FSInputFile(tmp_path, filename=meta["original_name"]),
                caption=f"Ваш файл: {meta['original_name']}\nID: {fid}"
            )
        finally:
            os.unlink(tmp_path)
        return

    # Запрос чужого файла – отправляем уведомление владельцу
    owner_info = users_db.get(owner_id)
    if not owner_info:
        await message.answer("❌ Владелец файла не найден в базе бота.")
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Одобрить", callback_data=f"approve_{fid}_{requester_id}")],
        [InlineKeyboardButton(text="❌ Отказать", callback_data=f"deny_{fid}_{requester_id}")]
    ])

    await bot.send_message(
        owner_id,
        f"📨 <b>Запрос файла</b>\n\n"
        f"Пользователь: {message.from_user.full_name}\n"
        f"Запрашивает файл: {meta['original_name']} (ID {fid})\n"
        f"Разрешить отправку?",
        parse_mode="HTML",
        reply_markup=keyboard
    )
    await message.answer("✅ Запрос отправлен владельцу. Он должен принять решение.")


# ========== Обработка callback-запросов ==========
@dp.callback_query()
async def handle_callback(callback: CallbackQuery):
    if callback.data.startswith("approve_"):
        _, fid, requester_id_str = callback.data.split("_")
        requester_id = int(requester_id_str)
        owner_id = callback.from_user.id

        # Проверка, что файл существует
        if fid not in files_meta:
            await callback.answer("Файл уже удалён из кэша")
            await callback.message.edit_text("❌ Файл не найден.")
            return

        meta = files_meta[fid]
        if meta["uploader_id"] != owner_id:
            await callback.answer("Это не ваш файл!")
            return

        # Скачиваем файл от имени владельца
        try:
            owner_api = get_user_client(owner_id)
            file_bytes = await owner_api.download_file(fid)
        except Exception as e:
            logger.exception("Ошибка скачивания при одобрении")
            await callback.answer("Не удалось скачать файл")
            await callback.message.edit_text(f"❌ Ошибка доступа к файлу: {e}")
            return

        # Отправляем запросившему
        with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{meta['original_name']}") as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name
        try:
            await bot.send_document(
                requester_id,
                FSInputFile(tmp_path, filename=meta["original_name"]),
                caption=f"✅ Владелец {callback.from_user.full_name} поделился файлом:\n{meta['original_name']}\nID: {fid}"
            )
        finally:
            os.unlink(tmp_path)

        await callback.message.edit_text(f"✅ Вы разрешили отправку файла {meta['original_name']} пользователю.")
        await callback.answer("Файл отправлен!")

    elif callback.data.startswith("deny_"):
        _, fid, requester_id_str = callback.data.split("_")
        requester_id = int(requester_id_str)
        owner_id = callback.from_user.id

        if fid not in files_meta:
            await callback.answer("Файл не найден")
            await callback.message.edit_text("❌ Файл уже не существует.")
            return

        meta = files_meta[fid]
        if meta["uploader_id"] != owner_id:
            await callback.answer("Это не ваш файл!")
            return

        await bot.send_message(requester_id, f"❌ Владелец отказал в выдаче файла ID {fid}.")
        await callback.message.edit_text(f"❌ Вы отказали в отправке файла {meta['original_name']}.")
        await callback.answer("Отказано")


# ========== Запуск ==========
async def main():
    os.makedirs(TEMP_DIR, exist_ok=True)
    load_users()
    load_files()
    logger.info("Бот запущен")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
@dp.callback_query()
async def process_callback(callback: CallbackQuery):
    try:
        if callback.data.startswith("approve_"):
            _, fid_str, req_str = callback.data.split("_")
            file_id = int(fid_str)
            requester_id = int(req_str)

            if file_id not in files_metadata:
                await callback.answer("Файл уже удалён")
                return

            meta = files_metadata[file_id]
            if callback.from_user.id != meta["uploader_id"]:
                await callback.answer("Это не твой файл!")
                return

            if not os.path.exists(meta["file_path"]):
                await callback.answer("Файл не найден на диске")
                return

            await bot.send_document(
                requester_id,
                FSInputFile(meta["file_path"]),
                caption=f"✅ Файл отправлен владельцем\nID: {file_id}\nНазвание: {meta['original_name']}"
            )

            await callback.message.edit_text(f"✅ Файл ID {file_id} отправлен пользователю.")
            await callback.answer("Отправлено!")

        elif callback.data.startswith("deny_"):
            _, fid_str, req_str = callback.data.split("_")
            file_id = int(fid_str)
            requester_id = int(req_str)

            if file_id not in files_metadata:
                await callback.answer("Файл уже удалён")
                return

            meta = files_metadata[file_id]
            if callback.from_user.id != meta["uploader_id"]:
                await callback.answer("Это не твой файл!")
                return

            await bot.send_message(requester_id, f"❌ Владелец отказал в выдаче файла ID {file_id}.")
            await callback.message.edit_text(f"❌ Доступ к файлу ID {file_id} запрещён.")
            await callback.answer("Отказано")

    except Exception as e:
        logger.exception("Ошибка callback")
        await callback.answer("Ошибка")


# Пуск
async def main():
    load_users()
    load_files()
    logger.info("🤖 Бот запущен")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())