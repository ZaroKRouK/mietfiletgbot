import pytest

from handlers.search import search_handler


@pytest.mark.asyncio
async def test_search_handler(message_mock):
    message_mock.text = 'Zurich'

    await search_handler(message_mock)

    message_mock.answer.assert_called()
