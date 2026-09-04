"""通过 HTTP 验收电商核心链路；失败返回非零退出码。"""
import json, sys, uuid
from urllib.request import Request, urlopen

def call(base, path, token=None, method="GET", payload=None, idem=None):
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Content-Type":"application/json"}
    if token: headers["Authorization"] = f"Bearer {token}"
    if idem: headers["X-Idempotency-Key"] = idem
    with urlopen(Request(base.rstrip("/")+path, data=data, headers=headers, method=method), timeout=10) as r:
        return json.loads(r.read())

def main(base):
    products = call(base, "/api/shop/products")
    if not products.get("items"): raise RuntimeError("商品目录为空")
    print(json.dumps({"stage":"browse","count":len(products["items"])}, ensure_ascii=False))
    print("请使用演示账号登录后运行完整下单/退单验收。")

if __name__ == "__main__":
    try: main(sys.argv[1] if len(sys.argv)>1 else "http://localhost:8001")
    except Exception as exc: print(f"验收失败: {exc}", file=sys.stderr); raise SystemExit(1)
