"""部署必须执行所有显式迁移，应用启动不能补建这些表。"""

from pathlib import Path


COMPOSE = Path(__file__).parents[2] / "deploy" / "compose" / "docker-compose.yml"


def test_customer_assistant_migration_is_in_compose_chain_before_api_and_worker():
    compose = COMPOSE.read_text(encoding="utf-8")

    assert "customer-assistant-migrate:" in compose
    assert "20260907_add_customer_assistant.sql:/migrations/20260907_add_customer_assistant.sql:ro" in compose
    assert '"-f", "/migrations/20260907_add_customer_assistant.sql"' in compose
    assert "customer-assistant-migrate:\n        condition: service_completed_successfully" in compose
