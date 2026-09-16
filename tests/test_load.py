"""Юнит-тесты загрузчика данных (app/services/load.py)."""
import pytest

from app.services import load
from app.services.load import get_attractions, get_quiz, get_snapshot, get_sources


def test_attractions_nonempty_list_of_dicts():
    items = get_attractions()
    assert isinstance(items, list) and len(items) >= 30
    assert all(isinstance(a, dict) for a in items)


def test_quiz_structure():
    quiz = get_quiz()
    assert isinstance(quiz, dict)
    assert quiz["intro"]
    assert len(quiz["questions"]) == 7


def test_sources_nonempty_with_required_keys():
    sources = get_sources()
    assert len(sources) >= 5
    for s in sources:
        assert s["id"] and s["name"] and s["url"].startswith("http")
        assert s["type"] in ("rss", "telegram")


def test_snapshot_has_items():
    snap = get_snapshot()
    assert isinstance(snap, dict)
    assert snap["items"]


def test_read_is_cached():
    """lru_cache: повторный вызов возвращает тот же объект, без чтения диска."""
    assert get_attractions() is get_attractions()
    assert get_quiz() is get_quiz()
    assert get_sources() is get_sources()
    assert get_snapshot() is get_snapshot()


def test_unknown_file_raises(tmp_path, monkeypatch):
    """Несуществующий JSON падает с понятной ошибкой, а не молча."""
    monkeypatch.setattr(load, "DATA_DIR", tmp_path)
    load._read.cache_clear()
    try:
        with pytest.raises(FileNotFoundError):
            load._read("missing.json")
    finally:
        load._read.cache_clear()
