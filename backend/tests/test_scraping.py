import pytest
from unittest.mock import AsyncMock
from pydantic import ValidationError

from app import models  # noqa: F401
from app.commerce_schemas import ProductDTO
from app.commerce_models import Product, ProductStatus, ScrapeRun, ScrapeRunStatus
from app.scraping.adapters import VivoAdapter, XiaomiAdapter
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
    assert str(rows[0].source_url) == "https://shop.vivo.com.cn/api/v1/home/index"


def test_vivo_adapter_parses_official_product_list_payload():
    rows = VivoAdapter().parse(
        '{"code":0,"data":{"dataList":[{"id":242665,"skuCode":"1234567",'
        '"skuName":"vivo Y6k 6GB+128GB","salePrice":1599,"brief":"大电池",'
        '"images":[{"smallPic":"https://shopstatic.vivo.com.cn/y6k.png"}]}]}}',
        "https://shop.vivo.com.cn/api/v1/home/index",
    )

    assert rows[0].sku == "1234567"
    assert rows[0].price == 1599
    assert rows[0].image_url == "https://shopstatic.vivo.com.cn/y6k.png"


def test_vivo_adapter_parses_official_home_accessory_cards():
    rows = VivoAdapter().parse(
        '{"data":{"navigateVos":[{"firstCategory":{"name":"手机充电"},"commoditySpus":['
        '{"spuId":10011368,"skuId":140725,"name":"闪充套装","price":"199",'
        '"brief":"数据线","imgUrl":"https://shopstatic.vivo.com.cn/charger.png",'
        '"link":"https://shop.vivo.com.cn/product/10011368?skuId=140725"}]}]}}',
        "https://shop.vivo.com.cn/api/v1/home/index",
    )

    assert rows[0].sku == "140725"
    assert rows[0].price == 199
    assert rows[0].name == "闪充套装"


def test_xiaomi_adapter_parses_official_shop_cards():
    rows = XiaomiAdapter().parse(
        '<li><a href="https://www.mi.com/shop/buy?product_id=24037">'
        '<img data-src="https://cdn.cnbj1.fds.api.mi-img.com/mi-mall/earbuds.png" />'
        '<div class="title">小米耳机</div><p class="price">99元起</p></a></li>',
        "https://www.mi.com/shop",
    )

    assert rows[0].brand == "xiaomi"
    assert rows[0].sku == "24037"
    assert rows[0].price == 99


def test_xiaomi_source_uses_official_accessory_search_page():
    assert XiaomiAdapter.source_url == "https://www.mi.com/shop/search?keyword=%E8%80%B3%E6%9C%BA"


def test_xiaomi_adapter_does_not_combine_fields_from_multiple_cards():
    rows = XiaomiAdapter().parse(
        '<li><a href="https://www.mi.com/shop/buy?product_id=1">'
        '<img data-src="https://cdn.cnbj1.fds.api.mi-img.com/mi-mall/nav.png" />'
        '<div class="title">无价格导航</div></a></li>'
        '<li><a href="https://www.mi.com/shop/buy?product_id=2">'
        '<img data-src="https://cdn.cnbj1.fds.api.mi-img.com/mi-mall/earbuds.png" />'
        '<div class="title">小米耳机</div><p class="price">99元起</p></a></li>',
        "https://www.mi.com/shop",
    )

    assert [row.sku for row in rows] == ["2"]


def test_xiaomi_adapter_parses_official_search_price_without_suffix():
    rows = XiaomiAdapter().parse(
        '<li><a href="https://www.mi.com/shop/buy?product_id=3">'
        '<img data-src="https://cdn.cnbj1.fds.api.mi-img.com/mi-mall/cable.png" />'
        '<div class="title">小米数据线</div><p class="price">159元</p></a></li>',
        "https://www.mi.com/shop",
    )

    assert rows[0].price == 159


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
