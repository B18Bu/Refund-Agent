"""消费者助手：只基于隔离商品目录提供可追溯答复。"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Callable

from sqlalchemy.orm import Session

from app.agents.llm import get_client
from app.commerce_models import Product, ProductStatus
from app.config import settings
from app.customer_assistant.models import CustomerCatalogChunk, CustomerPreferenceAudit
from app.customer_assistant.preferences import ALLOWED_PREFERENCE_KEYS, preference_values, privacy_enabled
from app.models import User
from app.security.gateway import CriticEngine, DLP, SecurityException


_RECOMMENDATION_RE = re.compile(r"推荐|适合.{0,12}(?:吗|的)|哪个好|选哪个|recommend", re.IGNORECASE)
_TERM_RE = re.compile(r"[a-z0-9]{2,}|[\u4e00-\u9fff]+", re.IGNORECASE)
_NO_EVIDENCE = "未找到足够的商品资料，暂时无法给出推荐。"
_BLOCKED = "该请求包含不安全指令，无法处理。"
_MODEL_FAILED = "商品资料暂时无法生成答复。"


@dataclass(frozen=True)
class CustomerAssistantReply:
    answer: str
    sources: list["CatalogEvidence"]
    personalized: bool


@dataclass(frozen=True)
class CatalogEvidence:
    source_url: str
    crawled_at: str | None


class CustomerAssistantService:
    def __init__(
        self,
        session: Session,
        *,
        generate: Callable[[dict], str] | None = None,
        critic: CriticEngine | None = None,
    ):
        self._session = session
        self._generate = generate or _generate_answer
        self._critic = critic or CriticEngine()

    def reply(self, user: User, message: str, context: dict | None = None) -> CustomerAssistantReply:
        masked_message, _entities = DLP.mask(message or "")
        try:
            self._critic.block_or_raise(masked_message, settings.SECURITY_INJECTION_THRESHOLD)
        except SecurityException:
            return CustomerAssistantReply(_BLOCKED, [], False)

        recommendation = bool(_RECOMMENDATION_RE.search(masked_message))
        evidence = self._search_catalog(masked_message, context)
        sources = [
            CatalogEvidence(
                source_url=chunk.source_url,
                crawled_at=chunk.crawled_at.isoformat() if chunk.crawled_at else None,
            )
            for chunk in evidence
        ]
        if not evidence:
            return CustomerAssistantReply(_NO_EVIDENCE, [], False)

        safe_evidence = [(chunk, DLP.mask(chunk.content)[0]) for chunk in evidence]
        preferences = self._allowed_preferences(user.id) if recommendation else {}
        material = {
            "question": masked_message,
            "evidence": [
                {"source_url": chunk.source_url, "content": content}
                for chunk, content in safe_evidence
            ],
            "preferences": preferences,
            "facts": {"intent": "recommendation" if recommendation else "catalog_question"},
        }
        try:
            answer = self._generate(material).strip()
        except Exception:
            return CustomerAssistantReply(_MODEL_FAILED, sources, bool(preferences))
        if not answer:
            return CustomerAssistantReply(_MODEL_FAILED, sources, bool(preferences))
        return CustomerAssistantReply(f"根据商品资料：{safe_evidence[0][1]}", sources, bool(preferences))

    def _search_catalog(self, message: str, context: dict | None) -> list[CustomerCatalogChunk]:
        terms: set[str] = set()
        for token in _TERM_RE.findall(message.lower()):
            if token[0].isascii():
                terms.add(token)
            else:
                terms.update(token[index:index + 2] for index in range(len(token) - 1))
        if not terms:
            return []
        query = (
            self._session.query(CustomerCatalogChunk)
            .join(Product, Product.id == CustomerCatalogChunk.product_id)
            .filter(Product.status == ProductStatus.ACTIVE)
        )
        scope = _catalog_scope(context)
        if scope is None:
            return []
        if "product_id" in scope:
            query = query.filter(CustomerCatalogChunk.product_id == scope["product_id"])
        if "brand" in scope:
            query = query.filter(Product.brand == scope["brand"])
        scored: list[tuple[int, int, CustomerCatalogChunk]] = []
        for chunk in query.all():
            content = chunk.content.lower()
            score = sum(term in content for term in terms)
            if score:
                scored.append((score, chunk.id, chunk))
        scored.sort(key=lambda item: (-item[0], item[1]))
        return [chunk for _score, _id, chunk in scored[:3]]

    def _allowed_preferences(self, user_id: int) -> dict[str, object]:
        if not privacy_enabled(self._session, user_id):
            self._session.add(CustomerPreferenceAudit(
                user_id=user_id,
                action="ASSISTANT_PREFERENCES_DENIED",
                summary={},
            ))
            self._session.commit()
            return {}
        values = {
            key: value
            for key in ALLOWED_PREFERENCE_KEYS
            if (value := preference_values(self._session, user_id, key))
        }
        self._session.add(CustomerPreferenceAudit(
            user_id=user_id,
            action="ASSISTANT_PREFERENCES_READ",
            summary={"preference_key_count": len(values)},
        ))
        self._session.commit()
        return values


def _catalog_scope(context: dict | None) -> dict[str, int | str] | None:
    if context is None:
        return {}
    if not isinstance(context, dict):
        return None
    scope: dict[str, int | str] = {}
    product_id = context.get("product_id")
    if product_id is not None:
        if not isinstance(product_id, int) or isinstance(product_id, bool) or product_id <= 0:
            return None
        scope["product_id"] = product_id
    if context.get("category") is not None:
        return None
    for key, limit in (("brand", 64),):
        value = context.get(key)
        if value is None:
            continue
        if not isinstance(value, str) or not 1 <= len(value.strip()) <= limit:
            return None
        scope[key] = value.strip()
    return scope


def _generate_answer(material: dict) -> str:
    """模型只接收脱敏问题、目录证据、白名单偏好和确定性事实。"""
    if settings.LLM_PROVIDER == "mock":
        return str(material["evidence"][0]["content"])
    client = get_client()
    if client is None:
        raise RuntimeError("DeepSeek 客户端不可用")
    response = client.chat.completions.create(
        model=settings.DEEPSEEK_MODEL,
        messages=[
            {"role": "system", "content": "仅根据给定商品证据回答；证据不足时明确说明，禁止编造。"},
            {"role": "user", "content": json.dumps(material, ensure_ascii=False)},
        ],
        temperature=0,
        timeout=10,
    )
    return response.choices[0].message.content or ""
