"""固定品牌来源适配器；输入格式优先支持公开 JSON，避免页面结构耦合。"""
import json
import re
from html import unescape
from app.commerce_schemas import ProductDTO

SOURCE_URLS = {
    "vivo": "https://shop.vivo.com.cn/api/v1/home/index",
    "xiaomi": "https://www.mi.com/shop/search?keyword=%E8%80%B3%E6%9C%BA",
    "generic": "https://example.com/products",
}
SOURCE_CONFIG = SOURCE_URLS


class _JsonAdapter:
    source_site = "generic"
    source_url = SOURCE_URLS["generic"]

    def parse(self, response_text: str, source_url: str) -> list[ProductDTO]:
        try:
            payload = json.loads(response_text)
            rows = payload.get("products", payload) if isinstance(payload, dict) else payload
            if not isinstance(rows, list):
                raise ValueError("商品数据格式错误")
        except (json.JSONDecodeError, ValueError) as exc:
            # 允许简单的 data-product JSON 属性作为静态页面降级格式
            rows = []
            for raw in re.findall(r'data-product=["\']([^"\']+)', response_text):
                rows.append(json.loads(raw))
            if not rows:
                raise ValueError("无法解析商品数据") from exc
        result = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            item = dict(row)
            item.setdefault("brand", self.source_site)
            # 来源 URL 是代码配置，不信任页面内容或调用方传入值。
            item["source_url"] = self.source_url
            item.setdefault("external_id", item.get("sku"))
            result.append(ProductDTO.model_validate(item))
        return result


class VivoAdapter(_JsonAdapter):
    source_site = "vivo"
    source_url = SOURCE_URLS["vivo"]

    def parse(self, response_text: str, source_url: str) -> list[ProductDTO]:
        payload = json.loads(response_text)
        navigation = payload.get("data", {}).get("navigateVos") if isinstance(payload, dict) else None
        if isinstance(navigation, list):
            result = []
            for category in navigation:
                if not isinstance(category, dict):
                    continue
                for row in category.get("commoditySpus") or []:
                    if not isinstance(row, dict):
                        continue
                    image_url = row.get("imgUrl")
                    result.append(ProductDTO(
                        brand=self.source_site,
                        sku=str(row["skuId"]),
                        name=row["name"],
                        price=row["price"],
                        source_url=self.source_url,
                        description=row.get("brief"),
                        image_url=image_url if isinstance(image_url, str) and image_url.startswith("https://") else None,
                        variant_name=row["name"],
                        external_id=str(row.get("spuId") or row["skuId"]),
                    ))
            if result:
                return result
        rows = payload.get("data", {}).get("dataList") if isinstance(payload, dict) else None
        if not isinstance(rows, list):
            return super().parse(response_text, source_url)
        result = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            images = row.get("images") or []
            image_url = images[0].get("smallPic") if images and isinstance(images[0], dict) else None
            result.append(ProductDTO(
                brand=self.source_site,
                sku=str(row["skuCode"]),
                name=row["skuName"],
                price=row["salePrice"],
                source_url=self.source_url,
                description=row.get("brief"),
                image_url=image_url if isinstance(image_url, str) and image_url.startswith("https://") else None,
                variant_name=row["skuName"],
                external_id=str(row.get("id") or row["skuCode"]),
            ))
        return result


class XiaomiAdapter(_JsonAdapter):
    source_site = "xiaomi"
    source_url = SOURCE_URLS["xiaomi"]

    _CARD = re.compile(r"<li\b[^>]*>(?P<card>.*?)</li>", re.DOTALL)
    _PRODUCT = re.compile(r'https://www\.mi\.com/shop/buy\?product_id=(?P<sku>\d+)')
    _IMAGE = re.compile(r'(?:data-src|src)="(?P<image>https://[^"]+)"')
    _TITLE = re.compile(r'<div\s+class="title">\s*(?P<name>.*?)\s*</div>', re.DOTALL)
    _PRICE = re.compile(r'<p\s+class="price">\s*(?P<price>[\d.]+)元(?:起)?\s*</p>')

    def parse(self, response_text: str, source_url: str) -> list[ProductDTO]:
        rows = []
        for card_match in self._CARD.finditer(response_text):
            card = card_match.group("card")
            product = self._PRODUCT.search(card)
            image = self._IMAGE.search(card)
            title = self._TITLE.search(card)
            price = self._PRICE.search(card)
            if not all((product, image, title, price)):
                continue
            rows.append(ProductDTO(
                brand=self.source_site,
                sku=product.group("sku"),
                name=unescape(re.sub(r"<[^>]+>", "", title.group("name")).strip()),
                price=price.group("price"),
                source_url=self.source_url,
                image_url=unescape(image.group("image")),
                variant_name=unescape(re.sub(r"<[^>]+>", "", title.group("name")).strip()),
                external_id=product.group("sku"),
            ))
        if not rows:
            raise ValueError("无法解析小米商城商品数据")
        return rows


class GenericAdapter(_JsonAdapter):
    source_site = "generic"
    source_url = SOURCE_URLS["generic"]


ADAPTERS = {"vivo": VivoAdapter, "xiaomi": XiaomiAdapter, "generic": GenericAdapter}

# 兼容调用方使用的显式品牌适配器命名。
VivoProductAdapter = VivoAdapter
XiaomiProductAdapter = XiaomiAdapter
GenericProductAdapter = GenericAdapter
