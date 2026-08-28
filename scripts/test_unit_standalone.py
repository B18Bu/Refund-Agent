#!/usr/bin/env python
"""核心单元逻辑独立测试脚本（不依赖 pytest）。

直接运行（项目根目录）：
    ./.venv/Scripts/python.exe scripts/test_unit_standalone.py

覆盖四组核心逻辑：
    1. 纯决策规则 decide()——金额 / OCR 置信度 / 欺诈分 / 舆情 红线与边界
    2. 认证安全 security——bcrypt 哈希校验 + JWT 签发/解码
    3. 幂等键 idempotency——Redis SET NX 首次创建 / 重复返回原值
    4. 分布式锁 locks——随机 token + Lua 比较释放，防误删他人新锁

无需启动后端、无需数据库；Redis 相关用 fakeredis 内存模拟。
"""
import os
import sys
from pathlib import Path

# 必须在导入 app.* 之前设置：testing 环境跳过 lifespan 的 DB 建表/种子
os.environ.setdefault("ENVIRONMENT", "testing")
os.environ.setdefault("LLM_PROVIDER", "mock")

BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND))

import fakeredis  # noqa: E402

from app.agents.decision_rules import decide  # noqa: E402
from app.idempotency import resolve_idempotency  # noqa: E402
from app.locks import acquire_approve_lock, release_approve_lock  # noqa: E402
from app.security import create_access_token, decode_token, hash_password, verify_password  # noqa: E402


# ---------- 极简测试执行器 ----------
_passed = 0
_failed = 0
_failures: list[tuple[str, object]] = []


def check(name: str, fn) -> None:
    global _passed, _failed
    try:
        fn()
        _passed += 1
        print(f"  [PASS] {name}")
    except AssertionError as e:
        _failed += 1
        _failures.append((name, e))
        print(f"  [FAIL] {name}: {e}")
    except Exception as e:  # noqa: BLE001 —— 独立脚本，任何异常都记录
        _failed += 1
        _failures.append((name, e))
        print(f"  [ERROR] {name}: {e!r}")


def eq(actual, expected, msg: str = "") -> None:
    assert actual == expected, f"{msg}：期望 {expected!r}，实际 {actual!r}"


# ---------- 1. 决策规则 ----------
def test_decision_rules() -> None:
    """任一红线命中 → HUMAN_REVIEW（宁挂勿错退），全部达标 → AUTO_REFUND。"""
    # 场景二：低风险 → 自动退款
    eq(decide(128.0, 0.9993, 20, "LOW"), "AUTO_REFUND", "低风险应自动退款")
    # 场景一：金额超上限 → 人工
    eq(decide(350.0, 0.9993, 20, "LOW"), "HUMAN_REVIEW", "金额超上限应人工")
    # OCR 低置信度 → 强制人工（置信度 < 0.6）
    eq(decide(128.0, 0.3, 20, "LOW"), "HUMAN_REVIEW", "OCR 低置信度应人工")
    # 高欺诈分 → 人工
    eq(decide(128.0, 0.99, 70, "LOW"), "HUMAN_REVIEW", "高欺诈分应人工")
    # 舆情非 LOW → 人工
    eq(decide(128.0, 0.99, 20, "HIGH"), "HUMAN_REVIEW", "舆情非 LOW 应人工")
    # 边界：恰好等于阈值不触发
    eq(decide(300.0, 0.6, 49, "LOW"), "AUTO_REFUND", "恰好边界应自动退款")
    # 边界 +0.01：触发红线
    eq(decide(300.01, 0.6, 49, "LOW"), "HUMAN_REVIEW", "金额略超上限应人工")
    eq(decide(128.0, 0.59, 49, "LOW"), "HUMAN_REVIEW", "置信度略低于阈值应人工")
    eq(decide(128.0, 0.6, 50, "LOW"), "HUMAN_REVIEW", "欺诈分达到阈值应人工")


# ---------- 2. 认证安全 ----------
def test_security() -> None:
    """bcrypt 哈希/校验 + JWT 签发/解码。"""
    h = hash_password("secret123")
    assert verify_password("secret123", h), "正确密码应校验通过"
    assert not verify_password("wrong", h), "错误密码应校验失败"
    assert h != "secret123", "哈希不应为明文"

    tok = create_access_token(1, "CS")
    payload = decode_token(tok)
    eq(payload["sub"], "1", "JWT sub 应为用户 ID")
    eq(payload["role"], "CS", "JWT role 应为角色")


# ---------- 3. 幂等键 ----------
def test_idempotency() -> None:
    """Redis SET NX：首次创建返回 None 并落库，重复提交返回首次工单标识。"""
    r = fakeredis.FakeRedis(decode_responses=True)
    key = "idem:1:test-key-001"
    eq(resolve_idempotency(r, key, "T-001"), None, "首次提交应返回 None")
    eq(r.get(key), "T-001", "首次应落库工单标识")
    eq(resolve_idempotency(r, key, "T-002"), "T-001", "重复提交应返回首次工单标识")


# ---------- 4. 分布式锁 ----------
def test_locks() -> None:
    """随机 token + Lua 比较释放（fakeredis 不支持 EVAL 时走 CAS 等价降级）。"""
    r = fakeredis.FakeRedis(decode_responses=True)
    token1 = acquire_approve_lock(r, "1001")
    assert token1, "加锁应成功并返回随机 token"
    eq(acquire_approve_lock(r, "1001"), None, "锁未释放时加锁应失败")
    eq(release_approve_lock(r, "1001", "wrong-token"), False, "错误 token 释放应失败")
    eq(r.get("lock:approve:1001"), token1, "错误 token 释放后锁应仍在")
    eq(release_approve_lock(r, "1001", token1), True, "正确 token 释放应成功")
    eq(r.get("lock:approve:1001"), None, "释放后锁应消失")
    token2 = acquire_approve_lock(r, "1001")
    assert token2 and token2 != token1, "重新加锁应得到新 token"


def main() -> int:
    print("===== 核心单元逻辑独立测试（不依赖 pytest） =====")
    print("[1/4] 决策规则 decide()")
    check("红线/边界共 9 例", test_decision_rules)
    print("[2/4] 认证安全 security")
    check("bcrypt 哈希/校验 + JWT", test_security)
    print("[3/4] 幂等键 idempotency")
    check("SET NX 首次/重复", test_idempotency)
    print("[4/4] 分布式锁 locks")
    check("token + Lua/CAS 比较释放", test_locks)

    print(f"\n===== 结果：{_passed} passed, {_failed} failed =====")
    for name, err in _failures:
        print(f"  ✗ {name}: {err}")
    return 1 if _failures else 0


if __name__ == "__main__":
    sys.exit(main())
