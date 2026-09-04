"""商品抓取、校验和缓存 upsert。"""
import asyncio
from datetime import datetime, timezone
import httpx
from sqlalchemy.orm import Session
from app.commerce_models import Product, ProductSource, ProductVariant, ProductStatus, ScrapeRun, ScrapeRunStatus
from app.scraping.adapters import ADAPTERS, SOURCE_URLS
from app.config import settings

_SOURCE_LOCKS = {name: asyncio.Lock() for name in ADAPTERS}


class ScrapeService:
    def __init__(self, db: Session):
        self.db = db

    async def scrape_source(self, source_site: str):
        if source_site not in ADAPTERS:
            raise ValueError(f"不支持的商品来源: {source_site}")
        async with _SOURCE_LOCKS[source_site]:
            adapter = ADAPTERS[source_site]()
            run = ScrapeRun(source_site=source_site, status=ScrapeRunStatus.RUNNING)
            self.db.add(run)
            self.db.commit()
            try:
                timeout = httpx.Timeout(10.0, connect=5.0)
                async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                    response = await client.get(SOURCE_URLS[source_site], headers={"User-Agent": "CommerceCatalog/1.0"})
                    if hasattr(response, "raise_for_status"):
                        response.raise_for_status()
                await asyncio.sleep(settings.SCRAPE_INTERVAL_SECONDS)
                products = adapter.parse(response.text, SOURCE_URLS[source_site])
                run.items_seen = len(products)
                for dto in products:
                    self._upsert(source_site, dto)
                run.items_upserted = len(products)
                run.status = ScrapeRunStatus.SUCCESS
            except Exception as exc:
                # 回滚本次 upsert，确保旧缓存不会因部分抓取结果被覆盖。
                error = str(exc)[:2000]
                self.db.rollback()
                run = self.db.get(ScrapeRun, run.id)
                run.status = ScrapeRunStatus.FAILED
                run.error_message = error
            run.ended_at = datetime.now(timezone.utc).replace(tzinfo=None)
            self.db.commit()
            return run

    async def run_scrape(self, source_site: str):
        """抓取单一来源的语义别名，供调度器调用。"""
        return await self.scrape_source(source_site)

    async def scrape_all(self, source_sites: list[str] | None = None):
        """按固定顺序抓取来源；单来源失败不会取消其他来源。"""
        results = []
        allowed = {x.strip() for x in settings.SCRAPE_ALLOWED_SOURCES.split(",") if x.strip()}
        for source_site in source_sites or [x for x in ADAPTERS if x in allowed]:
            if source_site not in allowed:
                raise ValueError(f"未允许的商品来源: {source_site}")
            results.append(await self.scrape_source(source_site))
        return results

    def _upsert(self, source_site, dto):
        external_id = dto.external_id or dto.sku
        source_url = SOURCE_URLS[source_site]
        source = (self.db.query(ProductSource)
                  .filter_by(source_site=source_site, external_id=external_id).first())
        if source:
            product = self.db.get(Product, source.product_id)
            source.source_url = source_url
            source.last_seen_at = datetime.utcnow()
        else:
            product = Product(brand=dto.brand, name=dto.name, model=dto.model,
                              description=dto.description, source_url=source_url,
                              source_site=source_site, image_url=str(dto.image_url) if dto.image_url else None,
                              status=ProductStatus.ACTIVE, last_synced_at=datetime.utcnow())
            self.db.add(product)
            self.db.flush()
            source = ProductSource(product_id=product.id, source_site=source_site,
                                   source_url=source_url, external_id=external_id,
                                   last_seen_at=datetime.utcnow())
            self.db.add(source)
        product.brand, product.name, product.model = dto.brand, dto.name, dto.model
        product.description = dto.description
        product.source_url, product.source_site = source_url, source_site
        product.image_url = str(dto.image_url) if dto.image_url else None
        product.status, product.last_synced_at = ProductStatus.ACTIVE, datetime.utcnow()
        variant = self.db.query(ProductVariant).filter_by(sku=dto.sku).first()
        if variant is None:
            self.db.add(ProductVariant(product_id=product.id, sku=dto.sku, variant_name=dto.variant_name,
                                       spec_json=dto.spec_json, price=dto.price, available=True))
        else:
            variant.product_id, variant.variant_name, variant.spec_json = product.id, dto.variant_name, dto.spec_json
            variant.price, variant.available = dto.price, True
