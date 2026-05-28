import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
API_BASE_URL = os.getenv("API_BASE_URL")
CLIENT_USERNAME = os.getenv("CLIENT_USERNAME")
CLIENT_PASSWORD = os.getenv("CLIENT_PASSWORD")

# Файлы для хранения данных
USERS_FILE = "users.json"
FILES_FILE = "files.json"
TEMP_DIR = "uploads"

# Проверка обязательных параметров
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не задан в .env")
if not CLIENT_USERNAME or not CLIENT_PASSWORD:
    raise ValueError("CLIENT_USERNAME и CLIENT_PASSWORD должны быть заданы в .env")