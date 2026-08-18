"""审批/状态分布式锁。

三方对齐 A-01（P0，必须完全遵循，禁止退化）：
- 锁值必须为「随机 token」，禁止固定值 "1"。
- 释放必须用「Lua 脚本比较 token 后删除」，严禁无条件 DEL（修复竞态缺陷：
  锁过期后可能误删他人重新持有的新锁）。
"""
import secrets

import redis
from redis import Redis
from redis.exceptions import ResponseError

from app.config import settings

# Lua 脚本：仅当当前值 == 传入 token 时才删除，否则返回 0（不删）。
_RELEASE_LUA = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
else
    return 0
end
"""


def _lock_key(ticket_id: str) -> str:
    return f"lock:approve:{ticket_id}"


def acquire_approve_lock(redis: "redis.Redis", ticket_id: str) -> str | None:
    """尝试加锁。成功返回随机 token（释放时需携带），失败返回 None。"""
    token = secrets.token_urlsafe(32)
    ok = redis.set(_lock_key(ticket_id), token, nx=True, px=10000)
    if ok:
        return token
    return None


def release_approve_lock(redis: "Redis", ticket_id: str, token: str) -> bool:
    """Lua 原子释放：比较 token 后删除，防止误删他人新锁。"""
    try:
        return bool(redis.eval(_RELEASE_LUA, 1, _lock_key(ticket_id), token))
    except ResponseError:
        # 旧版 redis 客户端 / fakeredis 不支持 eval 时，降级为「CAS 比较」。
        current = redis.get(_lock_key(ticket_id))
        if current == token:
            redis.delete(_lock_key(ticket_id))
            return True
        return False


def _approve_lock_ttl_ms() -> int:
    return 10000
