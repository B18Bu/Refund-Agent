"""仅在明确授权下，以有效订单确定性构建经过校验的结构化偏好。"""

from collections import Counter
from datetime import datetime, timedelta
from decimal import Decimal
import re
from typing import Any

from sqlalchemy.orm import Session

from app.commerce_service import eligible_order_items
from app.customer_assistant.models import (
    CustomerPreference,
    CustomerPreferenceAudit,
    CustomerPrivacySetting,
    IgnoredPreference,
)


ALLOWED_PREFERENCE_KEYS = frozenset({
    "category", "brand", "size", "budget", "purchase_frequency", "recent_products",
})
_SENSITIVE_TEXT = re.compile(r"(?:\d{7,}|地址|省|市|区|路|支付|银行卡|微信|聊天|order_no)", re.IGNORECASE)


def privacy_enabled(session: Session, user_id: int) -> bool:
    setting = _locked_privacy_setting(session, user_id)
    return bool(setting and setting.enabled)


def enable_privacy(session: Session, user_id: int) -> None:
    setting = _locked_privacy_setting(session, user_id)
    if setting is None:
        session.add(CustomerPrivacySetting(user_id=user_id, enabled=True))
    else:
        setting.enabled = True
    _audit(session, user_id, "PRIVACY_ENABLED")
    session.commit()


def disable_privacy(session: Session, user_id: int) -> None:
    setting = _locked_privacy_setting(session, user_id)
    if setting is None:
        session.add(CustomerPrivacySetting(user_id=user_id, enabled=False))
    else:
        setting.enabled = False
    session.query(CustomerPreference).filter(CustomerPreference.user_id == user_id).delete()
    _audit(session, user_id, "PRIVACY_DISABLED")
    session.commit()


def delete_preference(session: Session, user_id: int, preference_key: str) -> None:
    _validate_key(preference_key)
    ignored = session.query(IgnoredPreference).filter_by(user_id=user_id, preference_key=preference_key).first()
    if ignored is None:
        session.add(IgnoredPreference(user_id=user_id, preference_key=preference_key))
    session.query(CustomerPreference).filter_by(user_id=user_id, preference_key=preference_key).delete()
    _audit(session, user_id, "PREFERENCE_DELETED", preference_key)
    session.commit()


def restore_preference(session: Session, user_id: int, preference_key: str) -> None:
    _validate_key(preference_key)
    session.query(IgnoredPreference).filter_by(user_id=user_id, preference_key=preference_key).delete()
    _audit(session, user_id, "PREFERENCE_RESTORED", preference_key)
    session.commit()


def ignored_preference_keys(session: Session, user_id: int) -> set[str]:
    return {row.preference_key for row in session.query(IgnoredPreference).filter_by(user_id=user_id)}


def privacy_snapshot(session: Session, user_id: int) -> tuple[bool, list[tuple[str, Any, bool]], list[str]]:
    setting = _locked_privacy_setting(session, user_id)
    ignored = sorted(ignored_preference_keys(session, user_id))
    if setting is None or not setting.enabled:
        return False, [], ignored
    rows = session.query(CustomerPreference).filter_by(user_id=user_id).order_by(CustomerPreference.preference_key).all()
    preferences = [
        (row.preference_key, row.manual_value if row.manual_value is not None else row.automatic_value or [], row.manual_value is not None)
        for row in rows
    ]
    return True, preferences, ignored


def set_manual_preference(session: Session, user_id: int, preference_key: str, value: Any) -> None:
    _validate_value(preference_key, value)
    setting = _locked_privacy_setting(session, user_id)
    if setting is None or not setting.enabled:
        raise ValueError("未授权个性化偏好")
    preference = _preference(session, user_id, preference_key)
    if preference is None:
        preference = CustomerPreference(user_id=user_id, preference_key=preference_key, source_order_ids=[])
        session.add(preference)
    preference.manual_value = value
    _audit(session, user_id, "MANUAL_SET", preference_key, _value_summary(value))
    session.commit()


def preference_values(session: Session, user_id: int, preference_key: str) -> Any:
    _validate_key(preference_key)
    setting = _locked_privacy_setting(session, user_id)
    if setting is None or not setting.enabled:
        return []
    preference = _preference(session, user_id, preference_key)
    if preference is None:
        return []
    return preference.manual_value if preference.manual_value is not None else preference.automatic_value or []


def rebuild_preferences(session: Session, user_id: int, now: datetime) -> list[CustomerPreference]:
    setting = _locked_privacy_setting(session, user_id)
    if setting is None or not setting.enabled:
        return []

    items = eligible_order_items(session, user_id, now - timedelta(days=180))
    ignored = ignored_preference_keys(session, user_id)
    aggregates = _aggregate(items)
    rebuilt = []
    for key in ALLOWED_PREFERENCE_KEYS:
        if key in ignored:
            continue
        preference = _preference(session, user_id, key)
        aggregate = aggregates.get(key)
        if aggregate is None:
            if preference is not None:
                _clear_automatic(preference)
            continue
        value, source_order_ids, confidence = aggregate
        _validate_value(key, value)
        if preference is None:
            preference = CustomerPreference(user_id=user_id, preference_key=key)
            session.add(preference)
        preference.automatic_value = value
        preference.source_order_ids = source_order_ids
        preference.confidence = confidence
        rebuilt.append(preference)
    session.commit()
    return rebuilt


def _aggregate(items) -> dict[str, tuple[Any, list[int], float]]:
    if not items:
        return {}

    order_ids = sorted({item.order_id for item in items})
    categories = _ranked_strings(_value_for_key(item, "category") for item in items)
    brands = _ranked_strings(_value_for_key(item, "brand") for item in items)
    sizes = _ranked_strings(_value_for_key(item, "size") for item in items)
    prices = [float(Decimal(str(item.unit_price))) for item in items]
    recent_product_ids = list(dict.fromkeys(
        item.product_id for item in sorted(items, key=lambda item: (item.order.created_at, item.id), reverse=True)
    ))[:20]

    aggregates: dict[str, tuple[Any, list[int], float]] = {
        "budget": ({"min": min(prices), "max": max(prices), "currency": "CNY"}, order_ids, 1.0),
        "purchase_frequency": ({"orders": len(order_ids), "window_days": 180}, order_ids, 1.0),
        "recent_products": (recent_product_ids, order_ids, 1.0),
    }
    for key, values in (("category", categories), ("brand", brands), ("size", sizes)):
        if values:
            count = sum(1 for item in items if _value_for_key(item, key) is not None)
            aggregates[key] = (values, order_ids, count / len(items))
    return aggregates


def _ranked_strings(values) -> list[str]:
    counts = Counter(value for value in values if _is_allowed_label(value))
    return [value for value, _count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))]


def _value_for_key(item, key: str) -> Any:
    snapshot = _snapshot(item)
    if key != "size":
        return snapshot.get(key)
    spec_json = snapshot.get("spec_json")
    return spec_json.get("size") if isinstance(spec_json, dict) else snapshot.get("size")


def _snapshot(item) -> dict:
    snapshot = item.product_snapshot_json
    return snapshot if isinstance(snapshot, dict) else {}


def _locked_privacy_setting(session: Session, user_id: int) -> CustomerPrivacySetting | None:
    """在写入画像的同一事务中锁定授权行，避免关闭与旧写入交错。"""
    return (session.query(CustomerPrivacySetting)
            .populate_existing()
            .filter(CustomerPrivacySetting.user_id == user_id)
            .with_for_update()
            .one_or_none())


def _clear_automatic(preference: CustomerPreference) -> None:
    preference.automatic_value = None
    preference.source_order_ids = []
    preference.confidence = None


def _audit(session: Session, user_id: int, action: str, preference_key: str | None = None,
           summary: dict | None = None) -> None:
    session.add(CustomerPreferenceAudit(
        user_id=user_id,
        action=action,
        preference_key=preference_key,
        summary=summary or {},
    ))


def _value_summary(value: Any) -> dict:
    if isinstance(value, list):
        return {"value_kind": "string_list" if all(isinstance(item, str) for item in value) else "id_list", "value_count": len(value)}
    return {"value_kind": "object", "field_count": len(value)}


def _is_allowed_label(value: Any) -> bool:
    return isinstance(value, str) and 1 <= len(value) <= 64 and not _SENSITIVE_TEXT.search(value)


def _validate_key(preference_key: str) -> None:
    if preference_key not in ALLOWED_PREFERENCE_KEYS:
        raise ValueError("偏好键不允许")


def _validate_value(preference_key: str, value: Any) -> None:
    _validate_key(preference_key)
    if preference_key in {"category", "brand", "size"}:
        if (not isinstance(value, list) or not 1 <= len(value) <= 20
                or any(not isinstance(item, str) for item in value) or len(set(value)) != len(value)):
            raise ValueError("偏好值格式不合法")
        if any(not _is_allowed_label(item) for item in value):
            raise ValueError("偏好值包含不允许的内容")
        return
    if preference_key == "budget":
        if not isinstance(value, dict) or set(value) != {"min", "max", "currency"}:
            raise ValueError("偏好值格式不合法")
        lower, upper = value["min"], value["max"]
        if (isinstance(lower, bool) or isinstance(upper, bool) or not isinstance(lower, (int, float))
                or not isinstance(upper, (int, float)) or not 0 <= lower <= upper <= 999999 or value["currency"] != "CNY"):
            raise ValueError("偏好值格式不合法")
        return
    if preference_key == "purchase_frequency":
        if (not isinstance(value, dict) or set(value) != {"orders", "window_days"}
                or not isinstance(value["orders"], int) or isinstance(value["orders"], bool)
                or value["orders"] < 0 or value["window_days"] != 180):
            raise ValueError("偏好值格式不合法")
        return
    if (not isinstance(value, list) or not 1 <= len(value) <= 20 or len(set(value)) != len(value)
            or any(not isinstance(item, int) or isinstance(item, bool) or item <= 0 for item in value)):
        raise ValueError("偏好值格式不合法")


def _preference(session: Session, user_id: int, preference_key: str) -> CustomerPreference | None:
    return session.query(CustomerPreference).filter_by(user_id=user_id, preference_key=preference_key).first()
