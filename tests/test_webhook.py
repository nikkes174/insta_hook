import hashlib
import hmac
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.database import create_database, init_db
from app.webhook import normalize_events, process_instagram_event, verify_signature


def test_signature():
    body, secret = b'{"entry": []}', "secret"
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    assert verify_signature(body, f"sha256={digest}", secret)
    assert not verify_signature(body, "sha256=" + "0" * 64, secret)
    assert not verify_signature(body, None, secret)


def test_normalizes_both_event_shapes():
    assert len(normalize_events({"entry": [{"id": "1", "field": "comments", "value": {"id": "a"}}]})) == 1
    assert len(normalize_events({"entry": [{"id": "1", "changes": [{"field": "comments", "value": {"id": "b"}}]}]})) == 1
    assert normalize_events({"entry": [{"field": "likes", "value": {}}]}) == []


def test_keywords_case_insensitive_and_trimmed():
    settings = Settings(meta_verify_token="v", meta_access_token="a", meta_app_secret="s", meta_ig_user_id="1", meta_reply_keywords=" Инструкция, ссылка ")
    keywords = [word.casefold() for word in settings.meta_reply_keywords]
    assert any(word in "Нужна ИНСТРУКЦИЯ".casefold() for word in keywords)


@pytest.mark.anyio
async def test_verification_endpoint(monkeypatch):
    monkeypatch.setenv("META_VERIFY_TOKEN", "correct")
    monkeypatch.setenv("META_ACCESS_TOKEN", "access")
    monkeypatch.setenv("META_APP_SECRET", "secret")
    monkeypatch.setenv("META_IG_USER_ID", "1")
    from app import config
    config.get_settings.cache_clear()
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/meta/instagram/webhook?hub.mode=subscribe&hub.verify_token=correct&hub.challenge=12345")
        invalid = await client.get("/meta/instagram/webhook?hub.mode=subscribe&hub.verify_token=wrong&hub.challenge=12345")
    assert response.status_code == 200
    assert response.text == "12345"
    assert response.headers["content-type"].startswith("text/plain")
    assert invalid.status_code == 403


@pytest.mark.anyio
async def test_duplicate_is_replied_to_once_and_self_is_skipped(monkeypatch):
    settings = Settings(meta_verify_token="v", meta_access_token="a", meta_app_secret="s", meta_ig_user_id="own", meta_auto_reply_enabled=True, meta_auto_reply_message="hello")
    Path("data").mkdir(exist_ok=True)
    db_path = Path("data/test-webhook.db")
    db_path.unlink(missing_ok=True)
    engine, sessions = create_database(settings.model_copy(update={"database_url": "sqlite+aiosqlite:///./data/test-webhook.db"}))
    await init_db(engine)
    calls = []

    async def fake_reply(comment_id, message, current_settings):
        calls.append((comment_id, message))

    monkeypatch.setattr("app.webhook.reply_to_comment", fake_reply)
    payload = {"entry": [{"field": "comments", "value": {"id": "comment-1", "text": "hello", "from": {"id": "other"}}}]}
    await process_instagram_event(payload, sessions, settings)
    await process_instagram_event(payload, sessions, settings)
    own_payload = {"entry": [{"field": "comments", "value": {"id": "comment-2", "text": "hello", "from": {"id": "own"}}}]}
    await process_instagram_event(own_payload, sessions, settings)
    await engine.dispose()
    db_path.unlink(missing_ok=True)
    assert calls == [("comment-1", "hello")]
