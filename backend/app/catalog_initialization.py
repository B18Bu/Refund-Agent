"""商品目录完整抓取、门槛校验及最近成功快照管理。"""
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from sqlalchemy.orm import Session

# 注册用户/工单等基础表，确保独立目录测试的 metadata 完整。
from app import models  # noqa: F401
from app.commerce_models import CatalogState
from app.commerce_schemas import ProductDTO
from app.scraping.service import ScrapeService


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
    required = {"vivo", "oppo"}
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
    # 保留最近一次已发布目录；首次失败则明确保持未就绪。
    if state.status == CatalogStatus.READY.value:
        result.status = CatalogStatus.READY
        result.used_cached_catalog = True
        db.commit()
        return result
    state.status = CatalogStatus.INITIALIZATION_FAILED.value
    state.last_error_code = result.error_code
    db.commit()
    return result


def catalog_is_ready(db: Session) -> bool:
    row = db.get(CatalogState, 1)
    return bool(row and row.status == CatalogStatus.READY.value)
