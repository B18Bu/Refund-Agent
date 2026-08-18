"""幂等键：SET NX，首次返回 None，重复返回已存工单标识。"""
from typing import Any

import redis


def resolve_idempotency(redis: "redis.Redis", key: str, value: str) -> str | None:
    """SET NX + 24h TTL。首次写入返回 None，重复提交返回已存 value（ticket_id）。

    Redis 为幂等键的唯一事实来源；DB 侧联合唯一索引作兜底（见 models/迁移）。
    """
    ok = redis.set(key, value, nx=True, ex=86400)
    if ok:
        return None
    return redis.get(key)  # type: ignore[return-value]
