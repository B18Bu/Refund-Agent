"""目录初始化 Worker：启动即抓取，之后按固定周期刷新。"""
import asyncio
import logging
import time

from app.catalog_initialization import CatalogStatus, run_catalog_initialization
from app.customer_assistant.catalog_index import CustomerCatalogIndexer
from app.config import settings
from app.db import SessionLocal
from app.rag.embeddings import EmbeddingClient


logger = logging.getLogger("catalog-worker")


def run_once() -> None:
    db = SessionLocal()
    try:
        result = asyncio.run(run_catalog_initialization(db))
        if result.status == CatalogStatus.READY and not result.used_cached_catalog:
            CustomerCatalogIndexer(db, EmbeddingClient()).index()
            db.commit()
    except Exception:
        db.rollback()
        logger.exception("商品目录初始化失败")
    finally:
        db.close()


def run_forever() -> None:
    while True:
        run_once()
        time.sleep(settings.CATALOG_REFRESH_SECONDS)


if __name__ == "__main__":
    run_forever()
