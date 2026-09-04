"""商品目录完整抓取、门槛校验及最近成功快照管理。"""
import asyncio
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from sqlalchemy.orm import Session

# 注册用户/工单等基础表，确保独立目录测试的 metadata 完整。
from app import models  # noqa: F401
from app.commerce_models import CatalogState
from app.commerce_schemas import ProductDTO
from app.scraping.service import ScrapeService


CATALOG_SOURCES = ("vivo", "xiaomi")


class CatalogStatus(str, Enum):
    READY = "READY"
    INITIALIZATION_FAILED = "INITIALIZATION_FAILED"
    NOT_READY = "NOT_READY"


@dataclass
class CatalogResult:
    status: CatalogStatus
    error_code: str | None = None
    used_cached_catalog: bool = False


def validate_catalog_snapshot(snapshot: dict[str, list[ProductDTO]]) -> CatalogResult:
    required = {"vivo", "xiaomi"}
    if not required.issubset(snapshot):
        return CatalogResult(CatalogStatus.INITIALIZATION_FAILED, "BRAND_NOT_MET")
    all_items = []
    for brand in required:
        rows = snapshot.get(brand, [])
        if len(rows) < 20:
            return CatalogResult(CatalogStatus.INITIALIZATION_FAILED, "MINIMUM_SKU_NOT_MET")
        if not any(float(p.price) <= 300 for p in rows):
            return CatalogResult(CatalogStatus.INITIALIZATION_FAILED, "LOW_PRICE_SKU_NOT_MET")
        all_items.extend(rows)
    prices = [float(p.price) for p in all_items]
    if not any(p <= 300 for p in prices):
        return CatalogResult(CatalogStatus.INITIALIZATION_FAILED, "PRICE_BAND_NOT_MET")
    if not any(301 <= p <= 3000 for p in prices):
        return CatalogResult(CatalogStatus.INITIALIZATION_FAILED, "PRICE_BAND_NOT_MET")
    if not any(p > 3000 for p in prices):
        return CatalogResult(CatalogStatus.INITIALIZATION_FAILED, "PRICE_BAND_NOT_MET")
    return CatalogResult(CatalogStatus.READY)


def _state(db: Session) -> CatalogState:
    row = db.get(CatalogState, 1)
    if row is None:
        row = CatalogState(id=1, status=CatalogStatus.NOT_READY.value)
        db.add(row)
        db.flush()
    return row


def publish_successful_catalog(db: Session, snapshot: dict[str, list[ProductDTO]]) -> CatalogResult:
    result = validate_catalog_snapshot(snapshot)
    state = _state(db)
    if result.status != CatalogStatus.READY:
        state.status = CatalogStatus.INITIALIZATION_FAILED.value
        state.last_error_code = result.error_code
        db.commit()
        return result
    service = ScrapeService(db)
    try:
        for brand, rows in snapshot.items():
            for dto in rows:
                service._upsert(brand, dto)
        state.status = CatalogStatus.READY.value
        state.last_success_at = datetime.utcnow()
        state.last_error_code = None
        db.commit()
    except Exception:
        db.rollback()
        raise
    return result


def refresh_catalog(db: Session, snapshot: dict[str, list[ProductDTO]]) -> CatalogResult:
    result = validate_catalog_snapshot(snapshot)
    state = _state(db)
    if result.status == CatalogStatus.READY:
        return publish_successful_catalog(db, snapshot)
    return record_catalog_failure(db, result.error_code)


def record_catalog_failure(db: Session, error_code: str | None) -> CatalogResult:
    """记录失败；已有成功目录时仅更新诊断信息，不替换可售快照。"""
    state = _state(db)
    state.last_error_code = error_code
    if state.status == CatalogStatus.READY.value:
        db.commit()
        return CatalogResult(CatalogStatus.READY, error_code, used_cached_catalog=True)
    state.status = CatalogStatus.INITIALIZATION_FAILED.value
    db.commit()
    return CatalogResult(CatalogStatus.INITIALIZATION_FAILED, error_code)


async def run_catalog_initialization(db: Session) -> CatalogResult:
    """抓取固定双品牌快照，只有同轮完整通过门槛才允许发布。"""
    service = ScrapeService(db)
    results = await asyncio.gather(
        *(service.fetch_snapshot(source) for source in CATALOG_SOURCES),
        return_exceptions=True,
    )
    if any(isinstance(result, Exception) for result in results):
        return record_catalog_failure(db, "SOURCE_FETCH_FAILED")
    return refresh_catalog(db, dict(zip(CATALOG_SOURCES, results)))


def catalog_is_ready(db: Session) -> bool:
    row = db.get(CatalogState, 1)
    return bool(row and row.status == CatalogStatus.READY.value)
