import pytest

from handlers.callbacks import callback_handler


@pytest.mark.asyncio
async def test_callback_handler(callback_mock):
    await callback_handler(callback_mock)

    callback_mock.answer.assert_called_once()
