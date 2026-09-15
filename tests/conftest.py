import pytest
from fastapi.testclient import TestClient

from app import config
from app.main import app


@pytest.fixture()
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def _redirect_cache_file(tmp_path, monkeypatch):
    """Тесты не трогают реальный кэш в cache/."""
    monkeypatch.setattr(config, "NEWS_CACHE_FILE", tmp_path / "news_cache.json")
