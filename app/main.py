import json
import logging
from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.responses import PlainTextResponse

from .config import get_settings
from .database import create_database, init_db
from .webhook import process_instagram_event, verify_signature

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)
settings = get_settings()
engine, session_factory = create_database(settings)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await init_db(engine)
    logger.info("Instagram webhook service started")
    yield
    await engine.dispose()


app = FastAPI(title="Instagram Meta Webhook", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/meta/instagram/webhook", response_class=PlainTextResponse)
async def verify_webhook(request: Request) -> PlainTextResponse:
    params = request.query_params
    if params.get("hub.mode") != "subscribe" or params.get("hub.verify_token") != settings.meta_verify_token:
        return PlainTextResponse("Forbidden", status_code=403)
    return PlainTextResponse(params.get("hub.challenge", ""), status_code=200)


@app.post("/meta/instagram/webhook")
async def receive_webhook(request: Request, background_tasks: BackgroundTasks) -> dict[str, str]:
    body = await request.body()
    if not verify_signature(body, request.headers.get("X-Hub-Signature-256"), settings.meta_app_secret):
        logger.warning("Invalid webhook signature")
        raise HTTPException(status_code=401, detail="Invalid signature")
    try:
        payload = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise HTTPException(status_code=400, detail="Invalid JSON") from None
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid payload")
    logger.info("Valid Instagram webhook received")
    background_tasks.add_task(process_instagram_event, payload, session_factory, settings)
    return {"status": "ok"}
