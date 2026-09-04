from unittest.mock import AsyncMock, Mock

import pytest

from app.catalog_initialization import (
    CATALOG_SOURCES,
    CatalogStatus,
    publish_successful_catalog,
    refresh_catalog,
    run_catalog_initialization,
    validate_catalog_snapshot,
)
from app.config import Settings
from app.commerce_models import Product
from app.commerce_schemas import ProductDTO
from app.scraping.service import ScrapeService


def _product(brand: str, index: int, price: float) -> ProductDTO:
    return ProductDTO(
        brand=brand, sku=f"{brand}-{index}", name=f"{brand} 商品 {index}",
        price=price, source_url=f"https://www.{brand}.com/products/{index}",
    )


def _snapshot(oppo_count: int = 20):
    vivo_prices = [299, 999, 3999] + [1299] * 17
    oppo_prices = [199, 1599, 4999] + [1999] * (oppo_count - 3)
    return {
        "vivo": [_product("vivo", index, price) for index, price in enumerate(vivo_prices)],
        "xiaomi": [_product("xiaomi", index, price) for index, price in enumerate(oppo_prices)],
    }


def test_catalog_sources_are_vivo_and_xiaomi_only():
    assert CATALOG_SOURCES == ("vivo", "xiaomi")


def test_publish_requires_each_brand_twenty_skus_and_low_price(db_session):
    result = validate_catalog_snapshot(_snapshot(oppo_count=19))
    assert result.status == CatalogStatus.INITIALIZATION_FAILED
    assert result.error_code == "MINIMUM_SKU_NOT_MET"


def test_snapshot_requires_low_price_sku_per_brand():
    snapshot = _snapshot()
    snapshot["xiaomi"][0] = _product("xiaomi", 0, 301)
    result = validate_catalog_snapshot(snapshot)
    assert result.status == CatalogStatus.INITIALIZATION_FAILED
    assert result.error_code == "LOW_PRICE_SKU_NOT_MET"


def test_failed_refresh_keeps_last_successful_catalog(db_session):
    published = publish_successful_catalog(db_session, _snapshot())
    result = refresh_catalog(db_session, _snapshot(oppo_count=19))
    assert published.status == CatalogStatus.READY
    assert result.used_cached_catalog is True
    assert result.status == CatalogStatus.READY


@pytest.mark.asyncio
async def test_first_run_with_one_failed_brand_publishes_no_products(db_session, monkeypatch):
    monkeypatch.setattr(
        ScrapeService,
        "fetch_snapshot",
        AsyncMock(side_effect=[_snapshot()["vivo"], RuntimeError("oppo down")]),
    )

    result = await run_catalog_initialization(db_session)

    assert result.status == CatalogStatus.INITIALIZATION_FAILED
    assert result.error_code == "SOURCE_FETCH_FAILED"
    assert db_session.query(Product).count() == 0


def test_catalog_refresh_interval_defaults_to_daily():
    assert Settings().CATALOG_REFRESH_SECONDS == 86400


def test_catalog_worker_closes_session_after_single_initialization(monkeypatch):
    from app.worker import catalog_consumer

    db = Mock()
    monkeypatch.setattr(catalog_consumer, "SessionLocal", lambda: db)
    monkeypatch.setattr(catalog_consumer, "run_catalog_initialization", AsyncMock())

    catalog_consumer.run_once()

    db.close.assert_called_once()
