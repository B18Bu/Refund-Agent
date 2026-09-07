"""PostgreSQL 偏好授权行锁集成回归，不访问 public schema。"""

import threading
import uuid

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker

from app.customer_assistant.models import CustomerPreference, CustomerPrivacySetting
from app.models import Role, User


POSTGRES_URL = "postgresql+psycopg://postgres:postgres@localhost:5432/refund"


@pytest.mark.parametrize("operation", ["read", "write"])
def test_disable_waits_for_locked_preference_operation_then_hides_profile(monkeypatch, operation):
    """偏好读写持有授权行锁时，关闭必须等待；关闭提交后不能再读到偏好。"""
    schema = f"ca_lock_{uuid.uuid4().hex}"
    admin_engine = create_engine(POSTGRES_URL)
    service_engine = create_engine(POSTGRES_URL)
    _set_search_path(service_engine, schema)
    _create_schema(admin_engine, schema)
    Session = sessionmaker(bind=service_engine)
    reader = disabler = None
    try:
        with Session.begin() as session:
            user = User(username=f"lock-{uuid.uuid4().hex}", password_hash="unused", role=Role.CUSTOMER)
            session.add(user)
            session.flush()
            session.add(CustomerPrivacySetting(user_id=user.id, enabled=True))
            session.add(CustomerPreference(
                user_id=user.id,
                preference_key="brand",
                manual_value=["vivo"],
                source_order_ids=[],
            ))
            user_id = user.id

        from app.customer_assistant import preferences

        locked = threading.Event()
        release = threading.Event()
        disable_finished = threading.Event()
        failures = []
        original_preference = preferences._preference

        def pause_after_lock(session, current_user_id, preference_key):
            if current_user_id == user_id and preference_key == "brand":
                locked.set()
                if not release.wait(timeout=5):
                    raise TimeoutError("读取锁未被测试线程释放")
            return original_preference(session, current_user_id, preference_key)

        monkeypatch.setattr(preferences, "_preference", pause_after_lock)

        def operate_on_profile():
            nonlocal reader
            reader = Session()
            try:
                if operation == "read":
                    assert preferences.preference_values(reader, user_id, "brand") == ["vivo"]
                else:
                    preferences.set_manual_preference(reader, user_id, "brand", ["oppo"])
            except Exception as exc:  # pragma: no cover - 测试线程失败由主线程断言
                failures.append(exc)
            finally:
                reader.rollback()
                reader.close()

        def disable_profile():
            nonlocal disabler
            disabler = Session()
            try:
                preferences.disable_privacy(disabler, user_id)
                disable_finished.set()
            except Exception as exc:  # pragma: no cover - 测试线程失败由主线程断言
                failures.append(exc)
            finally:
                disabler.close()

        operation_thread = threading.Thread(target=operate_on_profile)
        operation_thread.start()
        assert locked.wait(timeout=5)
        disable_thread = threading.Thread(target=disable_profile)
        disable_thread.start()
        assert not disable_finished.wait(timeout=0.3)

        release.set()
        operation_thread.join(timeout=5)
        disable_thread.join(timeout=5)

        assert not operation_thread.is_alive()
        assert not disable_thread.is_alive()
        assert not failures
        assert disable_finished.is_set()
        with Session() as session:
            assert preferences.preference_values(session, user_id, "brand") == []
    finally:
        release.set() if "release" in locals() else None
        if reader is not None:
            reader.close()
        if disabler is not None:
            disabler.close()
        service_engine.dispose()
        _drop_schema(admin_engine, schema)
        admin_engine.dispose()


def _set_search_path(engine, schema: str) -> None:
    @event.listens_for(engine, "connect")
    def set_search_path(connection, _record):
        with connection.cursor() as cursor:
            cursor.execute(f"SET search_path TO {schema}")


def _create_schema(engine, schema: str) -> None:
    statements = [
        f"CREATE SCHEMA {schema}",
        f"CREATE TABLE {schema}.users (id SERIAL PRIMARY KEY, username VARCHAR(64) UNIQUE NOT NULL, password_hash VARCHAR(128) NOT NULL, role VARCHAR(32) NOT NULL, created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)",
        f"CREATE TABLE {schema}.customer_privacy_settings (user_id INTEGER PRIMARY KEY REFERENCES {schema}.users(id), enabled BOOLEAN NOT NULL DEFAULT FALSE, updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)",
        f"CREATE TABLE {schema}.customer_preferences (id SERIAL PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES {schema}.users(id), preference_key VARCHAR(64) NOT NULL, automatic_value JSONB, manual_value JSONB, source_order_ids JSONB NOT NULL DEFAULT '[]'::jsonb, confidence NUMERIC(5, 4), updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, CONSTRAINT uq_customer_preferences_user_key UNIQUE (user_id, preference_key))",
        f"CREATE TABLE {schema}.customer_preference_audits (id SERIAL PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES {schema}.users(id), action VARCHAR(32) NOT NULL, preference_key VARCHAR(64), summary JSONB NOT NULL DEFAULT '{{}}'::jsonb, created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)",
    ]
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))


def _drop_schema(engine, schema: str) -> None:
    with engine.begin() as connection:
        connection.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
