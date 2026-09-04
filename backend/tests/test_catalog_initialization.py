from app.catalog_initialization import (
    CatalogStatus,
    publish_successful_catalog,
    refresh_catalog,
    validate_catalog_snapshot,
)
from app.commerce_schemas import ProductDTO


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
        "oppo": [_product("oppo", index, price) for index, price in enumerate(oppo_prices)],
    }


def test_publish_requires_each_brand_twenty_skus_and_low_price(db_session):
    result = validate_catalog_snapshot(_snapshot(oppo_count=19))
    assert result.status == CatalogStatus.INITIALIZATION_FAILED
    assert result.error_code == "MINIMUM_SKU_NOT_MET"


def test_snapshot_requires_low_price_sku_per_brand():
    snapshot = _snapshot()
    snapshot["oppo"][0] = _product("oppo", 0, 301)
    result = validate_catalog_snapshot(snapshot)
    assert result.status == CatalogStatus.INITIALIZATION_FAILED
    assert result.error_code == "LOW_PRICE_SKU_NOT_MET"


def test_failed_refresh_keeps_last_successful_catalog(db_session):
    published = publish_successful_catalog(db_session, _snapshot())
    result = refresh_catalog(db_session, _snapshot(oppo_count=19))
    assert published.status == CatalogStatus.READY
    assert result.used_cached_catalog is True
    assert result.status == CatalogStatus.READY
