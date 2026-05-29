from unittest.mock import AsyncMock

import pytest


@pytest.fixture
def message_mock():
    message = AsyncMock()
    message.answer = AsyncMock()
    message.reply = AsyncMock()
    return message


@pytest.fixture
def callback_mock():
    callback = AsyncMock()
    callback.answer = AsyncMock()
    callback.message = AsyncMock()
    return callback


@pytest.fixture
def bot_mock():
    bot = AsyncMock()
    bot.send_message = AsyncMock()
    return bot
