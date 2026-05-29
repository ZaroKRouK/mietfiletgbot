import pytest

from states.search_state import SearchState


@pytest.mark.asyncio
async def test_state_exists():
    assert SearchState.waiting_for_city is not None
