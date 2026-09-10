"""消费者商品目录专用的固定维度 embedding 客户端。"""
from __future__ import annotations

import math
from typing import Protocol

import httpx


CATALOG_EMBEDDING_SERVICE_URL = "http://127.0.0.1:8080"
CATALOG_EMBEDDING_DIMENSION = 512


class CatalogEmbeddingUnavailable(RuntimeError):
    """消费者目录 embedding 服务不可用或返回不可信向量。"""


class HttpClient(Protocol):
    def post(self, url: str, json: dict, timeout: float): ...


class CatalogEmbeddingClient:
    def __init__(self, http_client: HttpClient | None = None):
        self._http_client = http_client or httpx.Client()

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            response = self._http_client.post(
                f"{CATALOG_EMBEDDING_SERVICE_URL}/embed", json={"texts": texts}, timeout=10.0
            )
            response.raise_for_status()
            vectors = response.json()["vectors"]
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            raise CatalogEmbeddingUnavailable("消费者目录 embedding 服务不可用") from exc
        if not isinstance(vectors, list) or len(vectors) != len(texts):
            raise CatalogEmbeddingUnavailable("embedding 返回数量不匹配")
        if any(
            not isinstance(vector, list)
            or len(vector) != CATALOG_EMBEDDING_DIMENSION
            or any(isinstance(item, bool) or not isinstance(item, (int, float)) or not math.isfinite(item) for item in vector)
            for vector in vectors
        ):
            raise CatalogEmbeddingUnavailable("embedding 必须包含 512 个有限数值")
        return [[float(item) for item in vector] for vector in vectors]
