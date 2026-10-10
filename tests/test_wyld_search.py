import io
import json

import pytest

from app import wyld_search


def test_search_requires_local_config(monkeypatch):
    monkeypatch.setenv("WYLD_SEARCH_URL", "https://remote.example")
    with pytest.raises(ValueError):
        wyld_search.search("travel Mumbai")


def test_search_uses_existing_v2_and_limits_fields(monkeypatch):
    monkeypatch.setenv("WYLD_SEARCH_URL", "http://127.0.0.1:8000")
    monkeypatch.setenv("WYLD_BACKEND_SECRET", "test-secret")

    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *_):
            self.close()

    def fake_open(request, timeout):
        assert request.full_url == "http://127.0.0.1:8000/search/v2"
        assert request.get_header("X-wyld-backend-secret") == "test-secret"
        assert json.loads(request.data)["query"] == "travel Mumbai"
        return Response(json.dumps({"total": 1, "items": [{"username": "real_creator", "fit_score": 86, "private_secret": "omit"}]}).encode())

    monkeypatch.setattr(wyld_search, "urlopen", fake_open)
    result = wyld_search.search("travel Mumbai")
    assert result["items"][0]["username"] == "real_creator"
    assert "private_secret" not in result["items"][0]
