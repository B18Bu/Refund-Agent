"""目录初始化 Worker：启动即抓取，之后按固定周期刷新。"""
import asyncio
import logging
import time

from app.catalog_initialization import run_catalog_initialization
from app.config import settings
from app.db import SessionLocal


logger = logging.getLogger("catalog-worker")


def run_once() -> None:
    db = SessionLocal()
    try:
        asyncio.run(run_catalog_initialization(db))
    except Exception:
        logger.exception("商品目录初始化失败")
    finally:
        db.close()


def run_forever() -> None:
    while True:
        run_once()
        time.sleep(settings.CATALOG_REFRESH_SECONDS)


if __name__ == "__main__":
    run_forever()
