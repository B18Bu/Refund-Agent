"""通过真实 HTTP 接口验收消费者咨询与隐私偏好闭环。"""

import json
import sys
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def call(base: str, path: str, *, token: str | None = None, method: str = "GET", payload=None):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(f"{base.rstrip('/')}{path}", data=data, headers=headers, method=method)
    with urlopen(request, timeout=10) as response:
        return response.status, json.loads(response.read())


def login(base: str, username: str) -> str:
    _status, payload = call(base, "/api/auth/login", method="POST", payload={
        "username": username,
        "password": "secret123",
    })
    return payload["access_token"]


def expect_forbidden(base: str, token: str) -> None:
    try:
        call(base, "/api/customer-assistant/privacy", token=token)
    except HTTPError as error:
        if error.code == 403:
            return
        raise RuntimeError(f"非消费者访问返回意外状态：{error.code}") from error
    raise RuntimeError("非消费者不应访问隐私接口")


def main(base: str) -> None:
    customer_token = login(base, "customer_01")
    staff_token = login(base, "customer_service_01")
    expect_forbidden(base, staff_token)

    _status, privacy = call(base, "/api/customer-assistant/privacy", token=customer_token, method="PUT", payload={"enabled": True})
    if not privacy["enabled"]:
        raise RuntimeError("未能开启偏好授权")

    _status, generic = call(base, "/api/customer-assistant/reply", token=customer_token, method="POST", payload={
        "message": "这款商品支持双卡吗？", "context": {},
    })
    if generic["personalized"]:
        raise RuntimeError("非推荐问题不得读取偏好")

    _status, privacy = call(base, "/api/customer-assistant/privacy/preferences/brand", token=customer_token, method="PUT", payload={"value": ["vivo"]})
    if not any(row["key"] == "brand" for row in privacy["preferences"]):
        raise RuntimeError("手动品牌偏好未保存")

    _status, recommendation = call(base, "/api/customer-assistant/reply", token=customer_token, method="POST", payload={
        "message": "推荐一款手机", "context": {},
    })
    if not recommendation["sources"]:
        raise RuntimeError("推荐验收需要可检索的商品目录证据")
    if not recommendation["personalized"]:
        raise RuntimeError("推荐问题未使用已授权偏好")

    _status, privacy = call(base, "/api/customer-assistant/privacy/preferences/brand", token=customer_token, method="DELETE")
    if "brand" not in privacy["ignored_keys"]:
        raise RuntimeError("删除偏好后未加入永久忽略列表")
    _status, privacy = call(base, "/api/customer-assistant/privacy/ignored/brand", token=customer_token, method="DELETE")
    if "brand" in privacy["ignored_keys"]:
        raise RuntimeError("恢复偏好后忽略键仍存在")

    _status, privacy = call(base, "/api/customer-assistant/privacy", token=customer_token, method="PUT", payload={"enabled": False})
    if privacy["enabled"] or privacy["preferences"]:
        raise RuntimeError("关闭授权后偏好画像未清除")
    print(json.dumps({"stage": "customer_assistant", "result": "passed"}, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main(sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8001")
    except Exception as error:
        print(f"验收失败：{error}", file=sys.stderr)
        raise SystemExit(1)
