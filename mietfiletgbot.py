import json
import asyncio
import logging
import os
from datetime import datetime
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, FSInputFile, CallbackQuery
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command

# Настройка первичная
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler("bot_logs.txt", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

TOKEN = "TOKEN"
USERS_FILE = "users.json"
FILES_FILE = "files.json"
UPLOADS_DIR = "uploads"

bot = Bot(token=TOKEN)
dp = Dispatcher()

# Пользователи
users = []


def load_users():
    global users
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            users = json.load(f)
    except:
        users = []


def save_users():
    try:
        with open(USERS_FILE, "w", encoding="utf-8") as f:
            json.dump(users, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Ошибка сохранения users.json: {e}")


def register_user(user_id: int, username: str = None, full_name: str = None):
    for user in users:
        if user["tg_id"] == user_id:
            user.update({
                "username": username,
                "full_name": full_name,
                "last_login": datetime.now().isoformat(),
                "login_count": user.get("login_count", 0) + 1
            })
            save_users()
            return user

    new_user = {
        "tg_id": user_id,
        "username": username,
        "full_name": full_name,
        "first_login": datetime.now().isoformat(),
        "last_login": datetime.now().isoformat(),
        "login_count": 1
    }
    users.append(new_user)
    save_users()
    return new_user


def get_user_name(user_id: int):
    for u in users:
        if u["tg_id"] == user_id:
            return u.get("full_name") or f"ID {user_id}", u.get("username")
    return f"ID {user_id}", None


# Файлы
files_metadata = {}
next_file_id = 1


def load_files():
    global files_metadata, next_file_id
    os.makedirs(UPLOADS_DIR, exist_ok=True)
    try:
        with open(FILES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        files_metadata = {item["id"]: item for item in data}
        next_file_id = max(files_metadata.keys(), default=0) + 1
    except:
        files_metadata = {}
        next_file_id = 1


def save_files():
    try:
        with open(FILES_FILE, "w", encoding="utf-8") as f:
            json.dump(list(files_metadata.values()), f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Ошибка сохранения files.json: {e}")


# Загрузка файлов
@dp.message(F.document)
async def upload_file(message: Message):
    register_user(message.from_user.id, message.from_user.username, message.from_user.full_name)

    document = message.document
    original_name = document.file_name or f"file_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    file_info = await bot.get_file(document.file_id)

    global next_file_id
    file_id = next_file_id
    next_file_id += 1

    safe_filename = f"{file_id}_{original_name}"
    file_path = os.path.join(UPLOADS_DIR, safe_filename)

    await bot.download_file(file_info.file_path, file_path)

    metadata = {
        "id": file_id,
        "original_name": original_name,
        "file_path": file_path,
        "uploader_id": message.from_user.id,
        "upload_time": datetime.now().isoformat(),
        "file_size": document.file_size
    }
    files_metadata[file_id] = metadata
    save_files()

    await message.answer(
        f"✅ <b>Файл успешно сохранён!</b>\n\n"
        f"Название: {original_name}\n"
        f"ID файла: <b>{file_id}</b>",
        parse_mode="HTML"
    )


# Команды

@dp.message(Command("start"))
async def cmd_start(message: Message):
    register_user(message.from_user.id, message.from_user.username, message.from_user.full_name)
    await message.answer(
        f"Привет, {message.from_user.full_name}!\n\n"
        f"Отправь мне файл — я сохраню его и выдам ID.\n"
        f"Напиши <code>/help</code> для списка всех команд.",
        parse_mode="HTML"
    )


@dp.message(Command("help"))
async def cmd_help(message: Message):
    text = (
        "<b>📋 Доступные команды:</b>\n\n"
        "• <code>/start</code> — приветствие\n"
        "• <code>/help</code> — показать это сообщение\n"
        "• <code>/files</code> — список всех файлов\n"
        "• <code>/myfiles</code> — только твои файлы\n"
        "• <code>/get ID</code> — запросить файл по ID\n"
        "• <code>/del ID</code> — удалить свой файл\n\n"
        "<b>Как работать:</b>\n"
        "1. Отправь любой файл\n"
        "2. Получи ID\n"
        "3. Другие могут запросить его через /get\n"
        "4. Ты можешь управлять своими файлами через /myfiles и /del"
    )
    await message.answer(text, parse_mode="HTML")


@dp.message(Command("files"))
async def cmd_files(message: Message):
    if not files_metadata:
        await message.answer("📂 Пока нет загруженных файлов.")
        return

    text = "<b>Все файлы в боте:</b>\n\n"
    for fid, meta in sorted(files_metadata.items()):
        owner_name, owner_user = get_user_name(meta["uploader_id"])
        size_mb = meta["file_size"] / (1024 * 1024)
        text += f"<b>ID {fid}</b> — {meta['original_name']}\n   └─ {owner_name}{f' (@{owner_user})' if owner_user else ''}\n   └─ {size_mb:.2f} МБ\n\n"

    await message.answer(text if len(text) < 4000 else text[:3900] + "\n...", parse_mode="HTML")


@dp.message(Command("myfiles"))
async def cmd_myfiles(message: Message):
    user_id = message.from_user.id
    register_user(user_id, message.from_user.username, message.from_user.full_name)

    my_files = {fid: meta for fid, meta in files_metadata.items() if meta["uploader_id"] == user_id}

    if not my_files:
        await message.answer("У тебя пока нет загруженных файлов.")
        return

    text = f"<b>Твои файлы ({len(my_files)} шт.):</b>\n\n"
    for fid, meta in sorted(my_files.items()):
        size_mb = meta["file_size"] / (1024 * 1024)
        text += (
            f"<b>ID {fid}</b> — {meta['original_name']}\n"
            f"   └─ Размер: {size_mb:.2f} МБ\n"
            f"   └─ Загружен: {meta['upload_time'][:10]}\n\n"
        )

    await message.answer(text, parse_mode="HTML")


@dp.message(Command("del"))
async def cmd_del(message: Message):
    user_id = message.from_user.id
    try:
        parts = message.text.strip().split(maxsplit=1)
        if len(parts) < 2:
            await message.answer("❌ Использование: <code>/del 123</code>", parse_mode="HTML")
            return

        file_id = int(parts[1].strip())

        if file_id not in files_metadata:
            await message.answer("❌ Файл с таким ID не найден.")
            return

        meta = files_metadata[file_id]

        if meta["uploader_id"] != user_id:
            await message.answer("❌ Это не твой файл. Ты можешь удалять только свои файлы.")
            return

        # Удаление файла с диска
        if os.path.exists(meta["file_path"]):
            os.remove(meta["file_path"])

        # Удаление из словаря
        del files_metadata[file_id]
        save_files()

        await message.answer(f"✅ Файл ID <b>{file_id}</b> успешно удалён.", parse_mode="HTML")
        logger.info(f"Файл {file_id} удалён пользователем {user_id}")

    except ValueError:
        await message.answer("❌ ID файла должен быть числом.")
    except Exception as e:
        logger.error(f"Ошибка при удалении файла: {e}")
        await message.answer("❌ Произошла ошибка при удалении.")


@dp.message(Command("get"))
async def cmd_get(message: Message):
    register_user(message.from_user.id, message.from_user.username, message.from_user.full_name)

    try:
        parts = message.text.strip().split(maxsplit=1)
        if len(parts) < 2:
            await message.answer("❌ Использование: <code>/get 123</code>", parse_mode="HTML")
            return

        file_id = int(parts[1].strip())
        if file_id not in files_metadata:
            await message.answer("❌ Файл не найден.")
            return

        metadata = files_metadata[file_id]
        requester_id = message.from_user.id
        owner_id = metadata["uploader_id"]

        if requester_id == owner_id:
            if not os.path.exists(metadata["file_path"]):
                await message.answer("❌ Файл удалён с диска.")
                return
            await message.answer_document(
                FSInputFile(metadata["file_path"]),
                caption=f"Ваш файл: {metadata['original_name']}\nID: {file_id}"
            )
            return

        # Запрос чужого файла
        owner_name, _ = get_user_name(owner_id)
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Одобрить", callback_data=f"approve_{file_id}_{requester_id}")],
            [InlineKeyboardButton(text="❌ Отказать", callback_data=f"deny_{file_id}_{requester_id}")]
        ])

        await bot.send_message(
            owner_id,
            f"📨 Запрос на файл ID <b>{file_id}</b>\n\n"
            f"От: {message.from_user.full_name}\n"
            f"Файл: {metadata['original_name']}\n\n"
            f"Разрешить отправить?",
            parse_mode="HTML",
            reply_markup=keyboard
        )

        await message.answer("✅ Запрос отправлен владельцу.")

    except Exception as e:
        logger.exception("Ошибка /get")
        await message.answer("❌ Ошибка при обработке запроса.")


# Фидбек
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