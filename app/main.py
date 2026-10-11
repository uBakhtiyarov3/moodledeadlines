"""Single process: Telegram bot (polling) + FastAPI (Mini Apps + API) + scheduler."""

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand, MenuButtonWebApp, WebAppInfo
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api import admin as admin_api
from app.api import student as student_api
from app.bot.handlers import UserMiddleware, router
from app.bot.keyboards import app_url
from app.config import get_settings
from app.db import init_db
from app.services import kb
from app.services import settings as rt
from app.services.reminders import dispatch_due_reminders
from app.services.sync import sync_all

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("app")
settings = get_settings()
WEB = Path(__file__).resolve().parent.parent / "webapp"


async def setup_bot(bot: Bot) -> None:
    for lang, cmds in {
        None: [("start", "Start"), ("deadlines", "Upcoming deadlines"), ("ai", "AI assistant"), ("lang", "Language")],
        "uz": [("start", "Boshlash"), ("deadlines", "Yaqin deadlinelar"), ("ai", "AI yordamchi"), ("lang", "Til")],
        "ru": [("start", "Старт"), ("deadlines", "Ближайшие дедлайны"), ("ai", "ИИ-помощник"), ("lang", "Язык")],
    }.items():
        await bot.set_my_commands([BotCommand(command=c, description=d) for c, d in cmds], language_code=lang)
    if settings.public_url.startswith("https://"):
        await bot.set_chat_menu_button(menu_button=MenuButtonWebApp(text="UWED", web_app=WebAppInfo(url=app_url())))


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await rt.load()
    await kb.rebuild()

    bot = Bot(settings.bot_token or "0:dummy", default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    app.state.bot = bot

    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(dispatch_due_reminders, "interval", minutes=1, args=[bot], max_instances=1, coalesce=True)
    scheduler.add_job(sync_all, "interval", minutes=5, max_instances=1, coalesce=True)

    polling = None
    if settings.run_bot and settings.bot_token:
        dp = Dispatcher()
        dp.message.outer_middleware(UserMiddleware())
        dp.callback_query.outer_middleware(UserMiddleware())
        dp.include_router(router)
        await setup_bot(bot)
        polling = asyncio.create_task(dp.start_polling(bot, handle_signals=False))
        scheduler.start()
        log.info("bot polling started")
    else:
        log.warning("BOT_TOKEN not set or RUN_BOT=false: API only, scheduler disabled")
    try:
        yield
    finally:
        if scheduler.running:
            scheduler.shutdown(wait=False)
        if polling:
            polling.cancel()
        await bot.session.close()


app = FastAPI(title="UWED Student Bot", lifespan=lifespan, docs_url=None, redoc_url=None)
app.include_router(student_api.router)
app.include_router(admin_api.router)


@app.get("/healthz")
async def health():
    return {"ok": True}


@app.get("/")
async def root():
    return RedirectResponse("/app/")


app.mount("/shared", StaticFiles(directory=WEB / "shared"), name="shared")
app.mount("/app", StaticFiles(directory=WEB / "student", html=True), name="student")
app.mount("/admin", StaticFiles(directory=WEB / "admin", html=True), name="admin")


def run() -> None:
    import uvicorn

    uvicorn.run(app, host=settings.host, port=settings.port, proxy_headers=True, forwarded_allow_ips="*")


if __name__ == "__main__":
    run()
