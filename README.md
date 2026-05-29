MietFileHost
============

_Этот репозиторий часть проекта по созданию файлообменника репозиторий хоста: [тык](https://github.com/Smkin32/mietfilehost)_

Тг бот на python с использованием библиотеки aiogram

Архитектура и зависимости
-------------------------
* Python
* Aiogram
* REST API

Как билдить?
------------
1. Настройте переменные окружения в .env
   ```
   BOT_TOKEN=[ВАШ ТОКЕН ТГ БОТА]
   API_BASE_URL=[URL ДЛЯ API]
   CLIENT_USERNAME=[ИМЯ ПОЛЬЗОВАТЕЛЯ ИЗ ХОСТА]
   CLIENT_PASSWORD=[ПАРОЛЬ ИЗ ХОСТА]
   ```
3. ``` docker build -t mietfiletgbot```
4. ```
   docker run -d \
   --name telegram-bot \
   -v bot_data:/app/data \
   mietfiletgbot
   ```
5. PROFIT!

Запуск тестов
-------------
Запустить тесты из папки tests с помощью pytest

Contact
-------
Andrey Semyonov tg @Smker32
