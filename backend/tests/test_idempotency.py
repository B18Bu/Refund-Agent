from app.idempotency import resolve_idempotency


def test_idempotency_first_submit_creates(redis_client):
    existing = resolve_idempotency(redis_client, "idem:1:k1", "T-001")
    assert existing is None          # 首次，创建成功
    assert redis_client.get("idem:1:k1") == "T-001"


def test_idempotency_duplicate_returns_original(redis_client):
    redis_client.set("idem:1:k1", "T-001", ex=86400)
    existing = resolve_idempotency(redis_client, "idem:1:k1", "T-002")
    assert existing == "T-001"       # 重复，返回首次工单 ID
