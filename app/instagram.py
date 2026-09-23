import logging
import httpx

from .config import Settings

logger = logging.getLogger(__name__)


async def reply_to_comment(comment_id: str, message: str, settings: Settings) -> None:
    url = f"https://graph.instagram.com/{settings.meta_graph_api_version}/{comment_id}/replies"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, data={"message": message, "access_token": settings.meta_access_token})
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        logger.error("Instagram Graph API returned HTTP error for comment_id=%s: %s", comment_id, exc.response.status_code)
        raise
    except httpx.HTTPError as exc:
        logger.error("Instagram Graph API request failed for comment_id=%s: %s", comment_id, exc)
        raise
    logger.info("Instagram reply sent successfully for comment_id=%s", comment_id)
