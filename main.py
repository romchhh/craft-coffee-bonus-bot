import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from config import token

logging.basicConfig(level=logging.INFO)
logging.getLogger("aiohttp.access").setLevel(logging.WARNING)

bot = Bot(token=token)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
_web_runner: dict = {}


async def main():
    from handlers.client_handlers.client_handlers import router as client_router, on_startup, on_shutdown
    from handlers.admin_handlers.admin_handlers import router as admin_router
    from handlers.admin_handlers.mailing_handlers import router as mailing_router
    from handlers.admin_handlers.links_handlers import router as links_router
    from handlers.admin_handlers.admin_management_handlers import router as admin_management_router
    from webapp_server import start_webapp, stop_webapp

    dp.include_router(client_router)
    dp.include_router(admin_router)
    dp.include_router(mailing_router)
    dp.include_router(links_router)
    dp.include_router(admin_management_router)

    async def _startup():
        await on_startup(None)
        await start_webapp(_web_runner)

    async def _shutdown():
        await stop_webapp(_web_runner)
        await on_shutdown(None)

    dp.startup.register(_startup)
    dp.shutdown.register(_shutdown)

    while True:
        try:
            await dp.start_polling(bot, skip_updates=True)
        except Exception as e:
            logging.error(f"Bot crashed with error: {e}", exc_info=True)
            try:
                await stop_webapp(_web_runner)
            except Exception:
                logging.exception("stop_webapp after crash")
            await asyncio.sleep(5)


if __name__ == "__main__":
    while True:
        try:
            asyncio.run(main())
        except Exception as e:
            logging.error(f"Critical error: {e}", exc_info=True)
            asyncio.run(asyncio.sleep(5))
