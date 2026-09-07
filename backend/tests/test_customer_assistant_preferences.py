"""消费者偏好必须以明确授权为前提，且删除操作永久生效。"""

from datetime import datetime

import pytest
from sqlalchemy.orm import sessionmaker

from app.commerce_models import Order, OrderItem, OrderStatus, Product, ProductStatus, ProductVariant
from app.models import Role, User


def _eligible_brand_item(db_session, user, order_no, brand, created_at, *, snapshot=None, price=100,
                         status=OrderStatus.COMPLETED):
    product = Product(brand=brand, name=f"{brand}-{order_no}", status=ProductStatus.ACTIVE)
    db_session.add(product)
    db_session.flush()
    variant = ProductVariant(product_id=product.id, sku=f"sku-{order_no}", variant_name="标准版", spec_json={}, price=100)
    order = Order(order_no=order_no, user_id=user.id, address_snapshot_json={}, status=status,
                  total_amount=price, created_at=created_at)
    db_session.add_all([variant, order])
    db_session.flush()
    db_session.add(OrderItem(order_id=order.id, product_id=product.id, variant_id=variant.id,
                             product_snapshot_json=snapshot or {"brand": brand}, quantity=1, unit_price=price))
    db_session.commit()


def test_privacy_is_disabled_by_default_and_prevents_aggregation(db_session):
    from app.customer_assistant.preferences import privacy_enabled, rebuild_preferences, preference_values

    user = User(username="privacy-default", password_hash="unused", role=Role.CUSTOMER)
    db_session.add(user)
    db_session.commit()
    _eligible_brand_item(db_session, user, "privacy-default", "vivo", datetime(2026, 9, 6))

    assert privacy_enabled(db_session, user.id) is False
    assert rebuild_preferences(db_session, user.id, datetime(2026, 9, 7)) == []
    assert preference_values(db_session, user.id, "brand") == []


def test_manual_preference_takes_precedence_over_automatic_value(db_session):
    from app.customer_assistant.preferences import (
        enable_privacy, preference_values, rebuild_preferences, set_manual_preference,
    )

    user = User(username="manual-precedence", password_hash="unused", role=Role.CUSTOMER)
    db_session.add(user)
    db_session.commit()
    _eligible_brand_item(db_session, user, "manual-precedence", "vivo", datetime(2026, 9, 6))
    enable_privacy(db_session, user.id)
    rebuild_preferences(db_session, user.id, datetime(2026, 9, 7))
    set_manual_preference(db_session, user.id, "brand", ["oppo"])

    assert preference_values(db_session, user.id, "brand") == ["oppo"]


def test_deleted_preference_is_not_rebuilt_until_restored(db_session):
    from app.customer_assistant.preferences import (
        delete_preference, enable_privacy, preference_values, rebuild_preferences, restore_preference,
    )

    user = User(username="permanent-ignore", password_hash="unused", role=Role.CUSTOMER)
    db_session.add(user)
    db_session.commit()
    _eligible_brand_item(db_session, user, "permanent-ignore", "vivo", datetime(2026, 9, 6))
    enable_privacy(db_session, user.id)
    delete_preference(db_session, user.id, "brand")
    rebuild_preferences(db_session, user.id, datetime(2026, 9, 7))

    assert preference_values(db_session, user.id, "brand") == []

    restore_preference(db_session, user.id, "brand")
    rebuild_preferences(db_session, user.id, datetime(2026, 9, 7))

    assert preference_values(db_session, user.id, "brand") == ["vivo"]


def test_disabling_privacy_clears_profile_and_sources_but_keeps_ignore(db_session):
    from app.customer_assistant.preferences import (
        delete_preference, disable_privacy, enable_privacy, ignored_preference_keys, rebuild_preferences,
    )
    from app.customer_assistant.models import CustomerPreference

    user = User(username="privacy-clear", password_hash="unused", role=Role.CUSTOMER)
    db_session.add(user)
    db_session.commit()
    _eligible_brand_item(db_session, user, "privacy-clear", "vivo", datetime(2026, 9, 6))
    enable_privacy(db_session, user.id)
    rebuild_preferences(db_session, user.id, datetime(2026, 9, 7))
    delete_preference(db_session, user.id, "size")

    disable_privacy(db_session, user.id)

    assert db_session.query(CustomerPreference).filter_by(user_id=user.id).count() == 0
    assert ignored_preference_keys(db_session, user.id) == {"size"}


def test_preference_schema_is_explicit_and_excludes_sensitive_data():
    from app.customer_assistant.models import CustomerPreference, CustomerPrivacySetting, IgnoredPreference

    columns = set(CustomerPreference.__table__.columns) | set(CustomerPrivacySetting.__table__.columns) | set(IgnoredPreference.__table__.columns)
    assert {"automatic_value", "manual_value", "source_order_ids", "updated_at", "confidence"} <= {
        column.name for column in CustomerPreference.__table__.columns
    }
    assert {"address", "payment", "chat", "order_snapshot"}.isdisjoint({column.name for column in columns})


def test_rebuild_clears_automatic_evidence_without_valid_orders_and_preserves_manual_value(db_session):
    from app.customer_assistant.models import CustomerPreference
    from app.customer_assistant.preferences import enable_privacy, rebuild_preferences, set_manual_preference

    user = User(username="clear-stale-automatic", password_hash="unused", role=Role.CUSTOMER)
    db_session.add(user)
    db_session.commit()
    _eligible_brand_item(db_session, user, "clear-stale-automatic", "vivo", datetime(2026, 9, 6))
    enable_privacy(db_session, user.id)
    rebuild_preferences(db_session, user.id, datetime(2026, 9, 7))
    set_manual_preference(db_session, user.id, "brand", ["oppo"])
    db_session.query(Order).filter_by(user_id=user.id).update({"status": OrderStatus.RETURN_COMPLETED})
    db_session.commit()

    rebuild_preferences(db_session, user.id, datetime(2026, 9, 7))

    preference = db_session.query(CustomerPreference).filter_by(user_id=user.id, preference_key="brand").one()
    assert preference.automatic_value is None
    assert preference.source_order_ids == []
    assert preference.confidence is None
    assert preference.manual_value == ["oppo"]


def test_rebuild_persists_only_whitelisted_structured_preference_keys(db_session):
    from app.customer_assistant.preferences import enable_privacy, rebuild_preferences

    user = User(username="all-structured-preferences", password_hash="unused", role=Role.CUSTOMER)
    db_session.add(user)
    db_session.commit()
    _eligible_brand_item(
        db_session, user, "structured-one", "vivo", datetime(2026, 9, 5), price=199,
        snapshot={"brand": "vivo", "category": "手机", "spec_json": {"size": "6.7英寸"}},
    )
    _eligible_brand_item(
        db_session, user, "structured-two", "vivo", datetime(2026, 9, 6), price=299,
        snapshot={"brand": "vivo", "category": "手机", "spec_json": {"size": "6.7英寸"}},
    )
    enable_privacy(db_session, user.id)

    preferences = {row.preference_key: row for row in rebuild_preferences(db_session, user.id, datetime(2026, 9, 7))}

    assert set(preferences) == {"category", "brand", "size", "budget", "purchase_frequency", "recent_products"}
    assert preferences["category"].automatic_value == ["手机"]
    assert preferences["brand"].automatic_value == ["vivo"]
    assert preferences["size"].automatic_value == ["6.7英寸"]
    assert preferences["budget"].automatic_value == {"min": 199.0, "max": 299.0, "currency": "CNY"}
    assert preferences["purchase_frequency"].automatic_value == {"orders": 2, "window_days": 180}
    assert preferences["recent_products"].automatic_value == [2, 1]
    assert all(row.source_order_ids for row in preferences.values())


def test_ignored_key_does_not_prevent_other_preferences_from_rebuilding(db_session):
    from app.customer_assistant.preferences import delete_preference, enable_privacy, rebuild_preferences

    user = User(username="per-key-ignore", password_hash="unused", role=Role.CUSTOMER)
    db_session.add(user)
    db_session.commit()
    _eligible_brand_item(db_session, user, "per-key-ignore", "vivo", datetime(2026, 9, 6),
                         snapshot={"brand": "vivo", "category": "手机"})
    enable_privacy(db_session, user.id)
    delete_preference(db_session, user.id, "brand")

    keys = {row.preference_key for row in rebuild_preferences(db_session, user.id, datetime(2026, 9, 7))}

    assert "brand" not in keys
    assert "category" in keys


def test_manual_preference_rejects_unknown_keys_and_sensitive_or_malformed_values(db_session):
    from app.customer_assistant.preferences import set_manual_preference

    user = User(username="preference-validation", password_hash="unused", role=Role.CUSTOMER)
    db_session.add(user)
    db_session.commit()

    with pytest.raises(ValueError, match="偏好键"):
        set_manual_preference(db_session, user.id, "address", ["北京市"])
    with pytest.raises(ValueError, match="偏好值"):
        set_manual_preference(db_session, user.id, "brand", [{"phone": "13800138000"}])
    with pytest.raises(ValueError, match="偏好值"):
        set_manual_preference(db_session, user.id, "budget", {"min": 100, "max": 99, "currency": "CNY"})


def test_rebuild_uses_180_day_window_and_excludes_refunded_orders(db_session):
    from app.customer_assistant.preferences import enable_privacy, rebuild_preferences, preference_values

    user = User(username="window-and-refund", password_hash="unused", role=Role.CUSTOMER)
    db_session.add(user)
    db_session.commit()
    _eligible_brand_item(db_session, user, "window-valid", "vivo", datetime(2026, 3, 11))
    _eligible_brand_item(db_session, user, "window-old", "oppo", datetime(2026, 3, 10))
    _eligible_brand_item(db_session, user, "window-refunded", "xiaomi", datetime(2026, 9, 6),
                         status=OrderStatus.RETURN_COMPLETED)
    enable_privacy(db_session, user.id)

    rebuild_preferences(db_session, user.id, datetime(2026, 9, 7))

    assert preference_values(db_session, user.id, "brand") == ["vivo"]


def test_privacy_disabled_rejects_manual_writes_and_never_returns_preferences(db_session):
    from app.customer_assistant.preferences import (
        disable_privacy, enable_privacy, preference_values, set_manual_preference,
    )

    user = User(username="privacy-disabled-manual", password_hash="unused", role=Role.CUSTOMER)
    db_session.add(user)
    db_session.commit()
    enable_privacy(db_session, user.id)
    set_manual_preference(db_session, user.id, "brand", ["vivo"])
    disable_privacy(db_session, user.id)

    with pytest.raises(ValueError, match="授权"):
        set_manual_preference(db_session, user.id, "brand", ["oppo"])
    assert preference_values(db_session, user.id, "brand") == []


def test_preference_actions_write_redacted_audit_records(db_session):
    from app.customer_assistant.models import CustomerPreferenceAudit
    from app.customer_assistant.preferences import (
        delete_preference, disable_privacy, enable_privacy, restore_preference, set_manual_preference,
    )

    user = User(username="preference-audit", password_hash="unused", role=Role.CUSTOMER)
    db_session.add(user)
    db_session.commit()
    enable_privacy(db_session, user.id)
    set_manual_preference(db_session, user.id, "brand", ["vivo"])
    delete_preference(db_session, user.id, "brand")
    restore_preference(db_session, user.id, "brand")
    disable_privacy(db_session, user.id)

    audits = db_session.query(CustomerPreferenceAudit).filter_by(user_id=user.id).order_by(CustomerPreferenceAudit.id).all()
    assert [audit.action for audit in audits] == [
        "PRIVACY_ENABLED", "MANUAL_SET", "PREFERENCE_DELETED", "PREFERENCE_RESTORED", "PRIVACY_DISABLED",
    ]
    assert audits[1].preference_key == "brand"
    assert audits[1].summary == {"value_kind": "string_list", "value_count": 1}
    assert {"vivo", "phone", "address", "payment", "chat"}.isdisjoint(
        {str(value).lower() for audit in audits for value in audit.summary.values()}
    )


def test_untrusted_snapshot_fields_are_skipped_without_blocking_other_valid_preferences(db_session):
    from app.customer_assistant.preferences import enable_privacy, rebuild_preferences, preference_values

    user = User(username="untrusted-snapshot", password_hash="unused", role=Role.CUSTOMER)
    db_session.add(user)
    db_session.commit()
    _eligible_brand_item(
        db_session, user, "untrusted-one", "vivo", datetime(2026, 9, 6),
        snapshot={"brand": "13800138000", "category": "手机", "spec_json": {"size": "x" * 65}},
    )
    _eligible_brand_item(
        db_session, user, "untrusted-two", "oppo", datetime(2026, 9, 6),
        snapshot={"brand": "oppo", "category": "手机", "spec_json": {"size": "6.7英寸"}},
    )
    enable_privacy(db_session, user.id)

    rebuild_preferences(db_session, user.id, datetime(2026, 9, 7))

    assert preference_values(db_session, user.id, "brand") == ["oppo"]
    assert preference_values(db_session, user.id, "category") == ["手机"]
    assert preference_values(db_session, user.id, "size") == ["6.7英寸"]


def test_preference_writes_lock_privacy_setting_before_reading_enabled_state(db_session, monkeypatch):
    from app.customer_assistant import preferences

    user = User(username="privacy-lock-protocol", password_hash="unused", role=Role.CUSTOMER)
    db_session.add(user)
    db_session.commit()
    locked_user_ids = []
    original = preferences._locked_privacy_setting

    def record_lock(session, user_id):
        locked_user_ids.append(user_id)
        return original(session, user_id)

    monkeypatch.setattr(preferences, "_locked_privacy_setting", record_lock)
    preferences.enable_privacy(db_session, user.id)
    preferences.set_manual_preference(db_session, user.id, "brand", ["vivo"])
    preferences.rebuild_preferences(db_session, user.id, datetime(2026, 9, 7))
    preferences.disable_privacy(db_session, user.id)

    assert locked_user_ids == [user.id, user.id, user.id, user.id]
    with pytest.raises(ValueError, match="授权"):
        preferences.set_manual_preference(db_session, user.id, "brand", ["oppo"])


def test_non_dict_order_snapshots_skip_text_fields_and_keep_all_valid_preference_types(db_session):
    from app.customer_assistant.preferences import enable_privacy, rebuild_preferences, preference_values

    user = User(username="non-dict-snapshots", password_hash="unused", role=Role.CUSTOMER)
    db_session.add(user)
    db_session.commit()
    _eligible_brand_item(db_session, user, "snapshot-valid", "vivo", datetime(2026, 9, 6), price=199,
                         snapshot={"brand": "vivo", "category": "手机", "spec_json": {"size": "6.7英寸"}})
    _eligible_brand_item(db_session, user, "snapshot-null", "oppo", datetime(2026, 9, 6), price=299)
    _eligible_brand_item(db_session, user, "snapshot-list", "xiaomi", datetime(2026, 9, 6), price=399)
    _eligible_brand_item(db_session, user, "snapshot-string", "honor", datetime(2026, 9, 6), price=499)
    items = db_session.query(OrderItem).order_by(OrderItem.id).all()
    items[1].product_snapshot_json = None
    items[2].product_snapshot_json = ["not", "an", "object"]
    items[3].product_snapshot_json = "not an object"
    db_session.commit()
    enable_privacy(db_session, user.id)

    keys = {row.preference_key for row in rebuild_preferences(db_session, user.id, datetime(2026, 9, 7))}

    assert keys == {"category", "brand", "size", "budget", "purchase_frequency", "recent_products"}
    assert preference_values(db_session, user.id, "brand") == ["vivo"]
    assert preference_values(db_session, user.id, "category") == ["手机"]
    assert preference_values(db_session, user.id, "size") == ["6.7英寸"]
    assert preference_values(db_session, user.id, "budget") == {"min": 199.0, "max": 499.0, "currency": "CNY"}
    assert preference_values(db_session, user.id, "purchase_frequency") == {"orders": 4, "window_days": 180}
    assert len(preference_values(db_session, user.id, "recent_products")) == 4


def test_preference_read_refreshes_locked_privacy_setting_after_another_session_disables(db_session):
    from app.customer_assistant.preferences import (
        disable_privacy, enable_privacy, preference_values, set_manual_preference,
    )

    user = User(username="privacy-read-lock", password_hash="unused", role=Role.CUSTOMER)
    db_session.add(user)
    db_session.commit()
    enable_privacy(db_session, user.id)
    set_manual_preference(db_session, user.id, "brand", ["vivo"])
    assert preference_values(db_session, user.id, "brand") == ["vivo"]

    OtherSession = sessionmaker(bind=db_session.get_bind())
    other_session = OtherSession()
    try:
        disable_privacy(other_session, user.id)
    finally:
        other_session.close()

    assert preference_values(db_session, user.id, "brand") == []


def test_preference_read_locks_privacy_setting_before_loading_profile(db_session, monkeypatch):
    from app.customer_assistant import preferences

    user = User(username="privacy-read-lock-protocol", password_hash="unused", role=Role.CUSTOMER)
    db_session.add(user)
    db_session.commit()
    preferences.enable_privacy(db_session, user.id)
    preferences.set_manual_preference(db_session, user.id, "brand", ["vivo"])
    calls = []
    original = preferences._locked_privacy_setting

    def record_lock(session, user_id):
        calls.append(user_id)
        return original(session, user_id)

    monkeypatch.setattr(preferences, "_locked_privacy_setting", record_lock)

    assert preferences.preference_values(db_session, user.id, "brand") == ["vivo"]
    assert calls == [user.id]
