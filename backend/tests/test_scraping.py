import pytest
from pydantic import ValidationError

from app.commerce_schemas import ProductDTO
from app.commerce_models import Product, ProductStatus, ScrapeRun, ScrapeRunStatus
from app.scraping.adapters import VivoAdapter
from app.scraping.service import ScrapeService


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
    assert str(rows[0].source_url) == "https://www.vivo.com.cn/products"


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
