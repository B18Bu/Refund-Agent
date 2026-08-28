#!/usr/bin/env python
"""接口防重（幂等）测试脚本——对真实 API 验证 `X-Idempotency-Key` 防重。

前置：后端 API 已启动（默认 http://localhost:8000，可用参数/环境变量 BASE_URL 覆盖），
     默认账号 cs1 / secret123 存在。
运行（项目根目录）：
    ./.venv/Scripts/python.exe scripts/test_interface_idempotency.py [BASE_URL]

验证点：
    T1 同 Key 重放 → 返回同一工单（金额保持首次 128）
    T2 不同 Key   → 生成不同工单
    T3 无 Key 两次 → 生成不同工单（证明防重依赖 X-Idempotency-Key）
    T4 并发不同 Key → 全部成功且互不相同（证明防重机制不串扰）

每个用例仅创建少量低额工单，不等待决策完成，仅校验工单身份一致性与防重语义。
"""
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("BASE_URL", "http://localhost:8000")
USER, PWD = "cs1", "secret123"

_passed = 0
_failed = 0
_failures: list[tuple[str, object]] = []


def req(method, path, payload=None, token=None, hdrs=None):
    r = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload).encode() if payload is not None else None,
        method=method,
    )
    r.add_header("Content-Type", "application/json")
    if token:
        r.add_header("Authorization", "Bearer " + token)
    if hdrs:
        for k, v in hdrs.items():
            r.add_header(k, v)
    try:
        with urllib.request.urlopen(r) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


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


def create_with_key(tok: str, key: str, amount: float = 128.0):
    return req("POST", "/api/tickets", {"amount": amount, "image_paths": []}, tok,
               {"X-Idempotency-Key": key})


def test_same_key_replay(tok: str) -> None:
    """T1：同 Key 重放返回同一工单，金额保持首次。"""
    k = f"it-{int(time.time())}-a"
    st, t1 = create_with_key(tok, k, 128.0)
    assert st == 200 and t1.get("ticket_id"), f"首次提交失败: {st} {t1}"
    st, t2 = create_with_key(tok, k, 999.0)  # 同 Key、不同金额的重放
    assert t2["ticket_id"] == t1["ticket_id"], \
        f"同 Key 应返回同一工单，实际 {t1['ticket_id']} vs {t2['ticket_id']}"
    st, detail = req("GET", f"/api/tickets/{t1['ticket_id']}", token=tok)
    assert detail["amount"] == 128.0, f"重放不应改变金额，实际 {detail['amount']}"
    print(f"      证据: Key={k} → ticket_id={t1['ticket_id']}（重放返回同单，金额保持 128.0）")


def test_different_key(tok: str) -> None:
    """T2：不同 Key 生成不同工单。"""
    k1, k2 = f"it-{int(time.time())}-b1", f"it-{int(time.time())}-b2"
    _, t1 = create_with_key(tok, k1)
    _, t2 = create_with_key(tok, k2)
    assert t1["ticket_id"] != t2["ticket_id"], "不同 Key 应生成不同工单"
    print(f"      证据: Key={k1} → {t1['ticket_id']}, Key={k2} → {t2['ticket_id']}")


def test_no_key(tok: str) -> None:
    """T3：无 Key 两次提交 → 不同工单（证明防重依赖 X-Idempotency-Key）。"""
    _, t1 = req("POST", "/api/tickets", {"amount": 128.0, "image_paths": []}, tok)
    _, t2 = req("POST", "/api/tickets", {"amount": 128.0, "image_paths": []}, tok)
    assert t1["ticket_id"] != t2["ticket_id"], "无 Key 两次应生成不同工单"
    print(f"      证据: 无 Key 两次 → {t1['ticket_id']} / {t2['ticket_id']}")


def test_concurrent_keys(tok: str) -> None:
    """T4：并发提交不同 Key，全部成功且互不相同。"""
    n = 5
    results: list[tuple[int, object]] = []

    def go(i: int) -> None:
        k = f"it-{int(time.time())}-c{i}"
        s, t = create_with_key(tok, k)
        results.append((s, t.get("ticket_id")))

    ths = [threading.Thread(target=go, args=(i,)) for i in range(n)]
    for x in ths:
        x.start()
    for x in ths:
        x.join()
    assert all(s == 200 for s, _ in results), f"存在失败提交: {results}"
    ids = [tid for _, tid in results]
    assert len(set(ids)) == n, f"并发不同 Key 应互不相同: {ids}"
    print(f"      证据: 并发 {n} 个不同 Key → 全部 200，工单互不相同 {ids}")


def main() -> int:
    print(f"===== 接口防重（X-Idempotency-Key）测试 @ {BASE} =====")
    st, login = req("POST", "/api/auth/login", {"username": USER, "password": PWD})
    if st != 200:
        print(f"[login] 失败: {st} {login}（请确认后端已启动且账号 cs1/secret123 存在）")
        return 2
    tok = login["access_token"]
    print(f"[login] {USER} OK")

    print("[T1] 同 Key 重放 → 同一工单")
    check("同 Key 重放返回同一工单且金额不变", lambda: test_same_key_replay(tok))
    print("[T2] 不同 Key → 不同工单")
    check("不同 Key 生成不同工单", lambda: test_different_key(tok))
    print("[T3] 无 Key → 不同工单")
    check("无 Key 两次生成不同工单", lambda: test_no_key(tok))
    print("[T4] 并发不同 Key → 互不相同")
    check("并发不同 Key 全部成功且互不相同", lambda: test_concurrent_keys(tok))

    print(f"\n===== 结果：{_passed} passed, {_failed} failed =====")
    for name, err in _failures:
        print(f"  ✗ {name}: {err}")
    return 1 if _failures else 0


if __name__ == "__main__":
    sys.exit(main())
