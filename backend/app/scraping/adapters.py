"""固定品牌来源适配器；输入格式优先支持公开 JSON，避免页面结构耦合。"""
import json
import re
from app.commerce_schemas import ProductDTO

SOURCE_URLS = {
    "vivo": "https://www.vivo.com.cn/products",
    "oppo": "https://www.oppo.com/cn/smartphones/",
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


class OppoAdapter(_JsonAdapter):
    source_site = "oppo"
    source_url = SOURCE_URLS["oppo"]


class GenericAdapter(_JsonAdapter):
    source_site = "generic"
    source_url = SOURCE_URLS["generic"]


ADAPTERS = {"vivo": VivoAdapter, "oppo": OppoAdapter, "generic": GenericAdapter}

# 兼容调用方使用的显式品牌适配器命名。
VivoProductAdapter = VivoAdapter
OppoProductAdapter = OppoAdapter
GenericProductAdapter = GenericAdapter
