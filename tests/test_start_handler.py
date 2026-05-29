import pytest

from handlers.start import start_handler


@pytest.mark.asyncio
async def test_start_handler(message_mock):
    await start_handler(message_mock)

    message_mock.answer.assert_called_once()
