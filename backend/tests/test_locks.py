"""分布式锁测试：重点验证 A-01「随机 token + Lua 比较后删除」的竞态修复。

策略：
- fakeredis 不支持 EVAL，故单元测试注入「与 _RELEASE_LUA 等价的 Python 语义」，
  验证调用方逻辑正确（比较 token 后删除，禁止无条件 DEL）。
- 真实 Redis 集成测试（test_real_redis_release_via_lua）在 Docker Redis 上强验证 Lua 脚本。
"""
import fakeredis

from app.locks import acquire_approve_lock, release_approve_lock

# 与 app.locks._RELEASE_LUA 等价的 Python 语义（测试注入用）
def _lua_semantics(redis, script, numkeys, *args):
    key, token = args[0], args[1]
    if redis.get(key) == token:
        return redis.delete(key)
    return 0


def test_approve_lock_exclusive(redis_client):
    token = acquire_approve_lock(redis_client, "T-001")
    assert token is not None
    # 第二把拿不到（不同 token 因 NX 失败）
    assert acquire_approve_lock(redis_client, "T-001") is None
    assert release_approve_lock(redis_client, "T-001", token) is True
    assert acquire_approve_lock(redis_client, "T-001") is not None


def test_release_mismatched_token_does_not_delete(monkeypatch, redis_client):
    """A 的 token 过期后 B 已持有新锁：A 用旧 token 释放必须失败且不能误删 B 的锁。"""
    # 注入 Lua 语义（fakeredis 不支持真实 EVAL）；实例方法 monkeypatch 需 lambda 转发
    monkeypatch.setattr(
        redis_client, "eval",
        lambda script, numkeys, *args: _lua_semantics(redis_client, script, numkeys, *args),
    )

    token_a = acquire_approve_lock(redis_client, "T-002")
    assert token_a is not None

    # 模拟锁过期后 B 重新加锁（强制覆盖为 B 的 token）
    redis_client.set("lock:approve:T-002", "token-b", nx=False, px=10000)
    token_b = "token-b"

    # A 尝试用旧 token 释放 → 必须失败（Lua 比较不通过）
    assert release_approve_lock(redis_client, "T-002", token_a) is False
    # B 的锁必须还在
    assert redis_client.get("lock:approve:T-002") == "token-b"

    # B 用自己 token 释放 → 成功
    assert release_approve_lock(redis_client, "T-002", token_b) is True


def test_release_uses_lua_not_plain_del(monkeypatch, redis_client):
    """确保释放路径确实走了 Lua 比较逻辑（禁无条件 DEL）。"""
    from app import locks

    evals_called = []

    def spy_eval(script, numkeys, *args, **kwargs):
        evals_called.append((script, args))
        return _lua_semantics(redis_client, script, numkeys, *args, **kwargs)

    monkeypatch.setattr(redis_client, "eval", spy_eval)
    # 记录是否有人绕过 Lua 直接调用 DEL（无条件 DEL 禁止）
    deletes_called = []
    monkeypatch.setattr(redis_client, "delete", lambda *a: deletes_called.append(a) or 1)

    token = acquire_approve_lock(redis_client, "T-003")
    assert token is not None
    assert release_approve_lock(redis_client, "T-003", token) is True
    assert len(evals_called) == 1, "释放必须走 Lua eval（比较 token 后删除）"
    script, args = evals_called[0]
    assert "del" in script.lower()
    assert args == ("lock:approve:T-003", token)
    # Lua 脚本内部的 DEL 是允许的（通过 EVAL）；但 release 路径不得直接调 DEL
    # —— 这里 eval 内部语义执行了 delete，属正常；关键是调用方走了 eval 而非裸 delete。
    assert len(deletes_called) == 1  # 该 DEL 来自 Lua 语义模拟，非调用方直接调用


def test_real_redis_release_via_lua():
    """真实 Redis（非 fakeredis）验证 Lua 释放语义。若环境无 Redis 则跳过。"""
    try:
        import redis
        r = redis.Redis.from_url("redis://localhost:6379/0", decode_responses=True)
        r.ping()
    except Exception:
        import pytest
        pytest.skip("本机无 Redis 服务，跳过真实 Redis 锁测试")

    token = acquire_approve_lock(r, "T-REAL")
    assert token is not None
    # 直接调用 Redis 原生 EVAL 验证脚本本体
    from app.locks import _RELEASE_LUA
    # 匹配 token 时删除成功
    assert bool(r.eval(_RELEASE_LUA, 1, "lock:approve:T-REAL", token)) is True
    assert r.get("lock:approve:T-REAL") is None
    r.close()
