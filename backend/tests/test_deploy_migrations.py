"""部署必须执行所有显式迁移，应用启动不能补建这些表。"""

from pathlib import Path
import os
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError


COMPOSE = Path(__file__).parents[2] / "deploy" / "compose" / "docker-compose.yml"
ENTRYPOINT = Path(__file__).parents[2] / "deploy" / "single-container" / "entrypoint.sh"
CUSTOMER_ASSISTANT_MIGRATION = Path(__file__).parents[1] / "migrations" / "20260907_add_customer_assistant.sql"
POSTGRES_URL = os.environ.get("POSTGRES_TEST_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/refund")


def test_customer_assistant_migration_runs_in_single_container_before_supervisor():
    entrypoint = ENTRYPOINT.read_text(encoding="utf-8")

    migration = "20260907_add_customer_assistant.sql"
    assert migration in entrypoint
    assert entrypoint.index(migration) < entrypoint.index("exec supervisord")


def test_customer_assistant_migration_adds_completed_to_a_legacy_postgres_order_status_enum():
    migration = CUSTOMER_ASSISTANT_MIGRATION.read_text(encoding="utf-8")

    assert "pg_attribute" in migration
    assert "pg_type" in migration
    assert "typtype = 'e'" in migration
    assert "ALTER TYPE %s ADD VALUE IF NOT EXISTS %L" in migration
    assert "COMPLETED" in migration


def test_customer_assistant_migration_supports_legacy_enum_and_varchar_order_statuses_in_postgres():
    engine = _postgres_engine_or_skip()
    enum_schema = f"ca_enum_{uuid.uuid4().hex}"
    varchar_schema = f"ca_varchar_{uuid.uuid4().hex}"
    try:
        _create_order_schema(engine, enum_schema, "legacy_order_status")
        _create_order_schema(engine, varchar_schema, "VARCHAR(32)")

        _apply_legacy_enum_compatibility(engine, enum_schema)
        _apply_legacy_enum_compatibility(engine, enum_schema)
        _apply_legacy_enum_compatibility(engine, varchar_schema)
        _apply_legacy_enum_compatibility(engine, varchar_schema)

        with engine.connect() as connection:
            enum_labels = connection.execute(text(f"""
                SELECT enum.enumlabel
                FROM pg_enum AS enum
                JOIN pg_type AS type ON type.oid = enum.enumtypid
                WHERE type.oid = '{enum_schema}.legacy_order_status'::REGTYPE
                ORDER BY enum.enumsortorder
            """)).scalars().all()
            varchar_type = connection.execute(text(f"""
                SELECT data_type
                FROM information_schema.columns
                WHERE table_schema = '{varchar_schema}'
                  AND table_name = 'orders'
                  AND column_name = 'status'
            """)).scalar_one()

        assert "COMPLETED" in enum_labels
        assert varchar_type == "character varying"
    finally:
        try:
            _drop_schema(engine, enum_schema)
        finally:
            try:
                _drop_schema(engine, varchar_schema)
            finally:
                engine.dispose()


def _create_order_schema(engine, schema: str, status_type: str) -> None:
    with engine.begin() as connection:
        connection.execute(text(f"CREATE SCHEMA {schema}"))
        if status_type == "legacy_order_status":
            connection.execute(text(f"CREATE TYPE {schema}.legacy_order_status AS ENUM ('CREATED', 'PAID_SIMULATED', 'RETURNING', 'RETURN_COMPLETED', 'CLOSED')"))
            status_type = f"{schema}.legacy_order_status"
        connection.execute(text(f"""
            CREATE TABLE {schema}.orders (
                id SERIAL PRIMARY KEY,
                status {status_type} NOT NULL DEFAULT 'CREATED',
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """))


def _postgres_engine_or_skip():
    engine = create_engine(POSTGRES_URL)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except OperationalError:
        engine.dispose()
        pytest.skip("PostgreSQL 集成服务不可用")
    return engine


def _drop_schema(engine, schema: str) -> None:
    with engine.begin() as connection:
        connection.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))


def _apply_legacy_enum_compatibility(engine, schema: str) -> None:
    migration = CUSTOMER_ASSISTANT_MIGRATION.read_text(encoding="utf-8")
    block_start = migration.index("DO $$")
    block_end = migration.index("END $$;", block_start) + len("END $$;")
    compatibility_block = migration[block_start:block_end]
    with engine.begin() as connection:
        connection.exec_driver_sql(f"SET LOCAL search_path TO {schema}, public")
        # Psycopg 会解析 DBAPI 占位符；迁移中的 PostgreSQL format() 占位符需在测试连接中转义。
        connection.exec_driver_sql(compatibility_block.replace("%", "%%"))
