import hashlib
import hmac
import logging
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from .config import Settings
from .instagram import reply_to_comment
from .models import ProcessedComment

logger = logging.getLogger(__name__)


def verify_signature(body: bytes, signature: str | None, app_secret: str) -> bool:
    if not signature or not signature.startswith("sha256="):
        return False
    supplied = signature[7:]
    if len(supplied) != 64:
        return False
    try:
        int(supplied, 16)
    except ValueError:
        return False
    expected = hmac.new(app_secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, supplied)


def normalize_events(payload: dict[str, Any]) -> list[dict[str, Any]]:
    events = []
    for entry in payload.get("entry", []):
        if not isinstance(entry, dict):
            continue
        candidates = [entry] if "field" in entry else [item for item in entry.get("changes", []) if isinstance(item, dict)]
        for candidate in candidates:
            if candidate.get("field") == "comments" and isinstance(candidate.get("value"), dict):
                events.append({"entry_id": entry.get("id"), "value": candidate["value"]})
    return events


async def claim_comment(session_factory, comment_id: str) -> bool:
    async with session_factory() as session:
        statement = sqlite_insert(ProcessedComment).values(comment_id=comment_id, status="processing")
        statement = statement.on_conflict_do_nothing(index_elements=[ProcessedComment.comment_id])
        result = await session.execute(statement)
        if result.rowcount == 1:
            await session.commit()
            return True
        current = await session.scalar(select(ProcessedComment.status).where(ProcessedComment.comment_id == comment_id))
        if current == "failed":
            retry = await session.execute(update(ProcessedComment).where(ProcessedComment.comment_id == comment_id, ProcessedComment.status == "failed").values(status="processing"))
            await session.commit()
            return retry.rowcount == 1
        await session.rollback()
        return False


async def set_status(session_factory, comment_id: str, status: str) -> None:
    async with session_factory() as session:
        await session.execute(update(ProcessedComment).where(ProcessedComment.comment_id == comment_id).values(status=status))
        await session.commit()


async def process_instagram_event(payload: dict[str, Any], session_factory, settings: Settings) -> None:
    for event in normalize_events(payload):
        value = event["value"]
        comment_id = value.get("id")
        if not comment_id:
            logger.warning("Ignoring comments event without comment_id")
            continue
        comment_id = str(comment_id)
        if not await claim_comment(session_factory, comment_id):
            logger.info("Duplicate or currently processing comment_id=%s", comment_id)
            continue
        author = value.get("from") if isinstance(value.get("from"), dict) else {}
        text = value.get("text") or ""
        username, author_id = author.get("username"), author.get("id")
        media = value.get("media") if isinstance(value.get("media"), dict) else {}
        logger.info("Processing comment_id=%s username=%s media_id=%s", comment_id, username, media.get("id"))
        try:
            if author_id is not None and str(author_id) == str(settings.meta_ig_user_id):
                logger.info("Skipping own Instagram comment_id=%s", comment_id)
            elif not settings.meta_auto_reply_enabled:
                logger.info("Auto reply disabled for comment_id=%s", comment_id)
            elif not settings.meta_auto_reply_message.strip():
                logger.warning("Auto reply skipped because META_AUTO_REPLY_MESSAGE is empty; comment_id=%s", comment_id)
            else:
                keywords = [keyword.casefold() for keyword in settings.meta_reply_keywords]
                if keywords and not any(keyword in str(text).casefold() for keyword in keywords):
                    logger.info("Keyword mismatch for comment_id=%s", comment_id)
                else:
                    await reply_to_comment(comment_id, settings.meta_auto_reply_message, settings)
            await set_status(session_factory, comment_id, "completed")
        except Exception:
            await set_status(session_factory, comment_id, "failed")
            logger.exception("Unexpected processing error for comment_id=%s", comment_id)
