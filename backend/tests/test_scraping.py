import pytest
from unittest.mock import AsyncMock
from pydantic import ValidationError

from app import models  # noqa: F401
from app.commerce_schemas import ProductDTO
from app.commerce_models import Product, ProductStatus, ScrapeRun, ScrapeRunStatus
from app.scraping.adapters import VivoAdapter
from app.scraping.service import ScrapeService


@pytest.mark.asyncio
async def test_fetch_snapshot_uses_fixed_source_and_does_not_write_products(db_session, monkeypatch):
    service = ScrapeService(db_session)
    monkeypatch.setattr(service, "_request_source", AsyncMock(return_value='{"products": []}'))

    rows = await service.fetch_snapshot("vivo")

    assert rows == []
    assert db_session.query(Product).count() == 0


def test_product_dto_rejects_invalid_source_name_and_price():
    with pytest.raises(ValidationError):
        ProductDTO(brand="vivo", sku="x", name="X", price=1, source_url="http://vivo.com/x")
    with pytest.raises(ValidationError):
        ProductDTO(brand="vivo", sku="x", name="", price=1, source_url="https://vivo.com/x")
    with pytest.raises(ValidationError):
        ProductDTO(brand="vivo", sku="x", name="X", price=0, source_url="https://vivo.com/x")


def test_vivo_adapter_parses_standard_json():
    rows = VivoAdapter().parse(
        '{"products":[{"sku":"x100","name":"X100","price":3999,"source_url":"https://attacker.invalid/x100"}]}',
        "https://attacker.invalid/products",
    )
    assert rows[0].brand == "vivo"
    assert rows[0].sku == "x100"
    assert str(rows[0].source_url) == "https://shop.vivo.com.cn/api/v1/prodList/phone?pageNum=1&pageSize=100"


def test_vivo_adapter_parses_official_product_list_payload():
    rows = VivoAdapter().parse(
        '{"code":0,"data":{"dataList":[{"id":242665,"skuCode":"1234567",'
        '"skuName":"vivo Y6k 6GB+128GB","salePrice":1599,"brief":"大电池",'
        '"images":[{"smallPic":"https://shopstatic.vivo.com.cn/y6k.png"}]}]}}',
        "https://shop.vivo.com.cn/api/v1/prodList/phone?pageNum=1&pageSize=100",
    )

    assert rows[0].sku == "1234567"
    assert rows[0].price == 1599
    assert rows[0].image_url == "https://shopstatic.vivo.com.cn/y6k.png"


@pytest.mark.asyncio
async def test_scrape_failure_keeps_active_cache(db_session, monkeypatch):
    old = Product(brand="vivo", name="X100", status=ProductStatus.ACTIVE)
    db_session.add(old)
    db_session.commit()

    class FailingClient:
        async def get(self, *args, **kwargs):
            raise RuntimeError("network down")

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr("app.scraping.service.httpx.AsyncClient", lambda **kwargs: FailingClient())
    run = await ScrapeService(db_session).scrape_source("vivo")
    db_session.refresh(old)
    assert run.status == ScrapeRunStatus.FAILED
    assert old.status == ProductStatus.ACTIVE
