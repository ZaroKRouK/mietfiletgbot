from utils.helpers import normalize_city


def test_normalize_city():
    result = normalize_city('  Zurich  ')

    assert result == 'zurich'
