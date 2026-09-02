#!/usr/bin/env python
"""两大场景端到端联调 + 并发审批竞态验证（真实 HTTP 服务）。

前置：docker compose --env-file .env -f deploy/compose/docker-compose.yml up -d postgres redis；启动 api 与 worker；LLM_PROVIDER=mock。
用法：python scripts/scenario_e2e.py [BASE_URL]
"""
import json
import mimetypes
import pathlib
import sys
import threading
import time
import uuid
import urllib.error
import urllib.request
from collections import Counter
from PIL import Image, ImageDraw, ImageFont

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8001"
APPROVAL_ENDPOINT = "/approval"
ROOT = pathlib.Path(__file__).resolve().parents[1]
SAMPLE_DIR = ROOT / "docs" / "assets" / "samples"


def build_multipart_body(boundary: str, amount: float, image_path: pathlib.Path) -> bytes:
    data = image_path.read_bytes()
    content_type = mimetypes.guess_type(image_path.name)[0] or "application/octet-stream"
    parts = [
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"amount\"\r\n\r\n{amount}\r\n".encode(),
        (
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"files\"; filename=\"{image_path.name}\"\r\n"
            f"Content-Type: {content_type}\r\n\r\n"
        ).encode() + data + b"\r\n",
        f"--{boundary}--\r\n".encode(),
    ]
    return b"".join(parts)


def submit_ticket_with_file(amount: float, image_path: pathlib.Path, token: str, headers=None):
    boundary = f"----refund-{uuid.uuid4().hex}"
    request = urllib.request.Request(
        BASE + "/api/tickets/with-files",
        data=build_multipart_body(boundary, amount, image_path),
        method="POST",
    )
    request.add_header("Authorization", "Bearer " + token)
    request.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    for key, value in (headers or {}).items():
        request.add_header(key, value)
    with urllib.request.urlopen(request) as response:
        return response.status, json.loads(response.read().decode())


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


def make_image(path: pathlib.Path, line1: str, line2: str) -> None:
    img = Image.new("RGB", (600, 200), "white")
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 40)
    except Exception:
        font = ImageFont.load_default()
    d.text((30, 40), line1, fill="black", font=font)
    d.text((30, 110), line2, fill="black", font=font)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)


def main() -> int:
    tok = req("POST", "/api/auth/login", {"username": "cs1", "password": "secret123"})[1]["access_token"]
    sv_tok = req("POST", "/api/auth/login", {"username": "sv1", "password": "secret123"})[1]["access_token"]
    print("[login] OK")

    # ===== 场景一：350 元 + 破损发票 → 挂起 → 主管 APPROVE → APPROVED =====
    invoice_path = SAMPLE_DIR / "invoice350.png"
    make_image(invoice_path, "破损商品退款申请", "金额350.00元")
    st, t = submit_ticket_with_file(350.0, invoice_path, tok)
    tid1 = t["ticket_id"]
    time.sleep(12)  # Worker 真实 OCR
    st, d = req("GET", f"/api/tickets/{tid1}", token=tok)
    assert d["status"] == "SUSPENDED", f"S1 应挂起，实际 {d['status']}"
    assert d["ocr_confidence"] and d["ocr_confidence"] > 0.6, "S1 OCR 置信度过低"
    print(f"[S1] {tid1} 挂起 [OK]  OCR置信度={d['ocr_confidence']} OCR={d['ocr_text']!r}")

    st, apr = req("POST", f"/api/tickets/{tid1}{APPROVAL_ENDPOINT}",
                  {"action": "APPROVE", "comment": "情况属实，批准退款"}, sv_tok)
    assert st == 200, f"S1 审批应 200，实际 {st}: {apr}"
    time.sleep(8)
    st, d = req("GET", f"/api/tickets/{tid1}", token=tok)
    assert d["outcome"] == "APPROVED", f"S1 终态应 APPROVED，实际 {d['outcome']}"
    print(f"[S1] {tid1} APPROVED [OK]")

    # ===== 场景二：128 元 + 清晰商品图 → 自动退款 =====
    goods_path = SAMPLE_DIR / "goods128.png"
    make_image(goods_path, "正品全新商品", "订单号128元")
    idem = f"s2-{int(time.time())}"
    st, t = submit_ticket_with_file(128.0, goods_path, tok, {"X-Idempotency-Key": idem})
    tid2 = t["ticket_id"]
    # 幂等重放
    st2, t2 = req("POST", "/api/tickets", {"amount": 999.0}, tok, {"X-Idempotency-Key": idem})
    assert t2["ticket_id"] == tid2, "S2 幂等重放应返回同工单"
    time.sleep(12)
    st, d = req("GET", f"/api/tickets/{tid2}", token=tok)
    assert d["outcome"] == "AUTO_REFUNDED", f"S2 终态应 AUTO_REFUNDED，实际 {d['outcome']}"
    print(f"[S2] {tid2} AUTO_REFUNDED [OK]  (OCR置信度={d['ocr_confidence']})")

    # ===== 并发审批竞态：恰好 1 个成功 =====
    st, t = req("POST", "/api/tickets", {"amount": 350.0, "image_paths": []}, tok)
    tid3 = t["ticket_id"]
    time.sleep(8)
    st, d = req("GET", f"/api/tickets/{tid3}", token=tok)
    assert d["status"] == "SUSPENDED"
    results = []
    def approve(i):
        s, _ = req("POST", f"/api/tickets/{tid3}{APPROVAL_ENDPOINT}", {"action": "APPROVE"}, sv_tok)
        results.append(s)
    ths = [threading.Thread(target=approve, args=(i,)) for i in range(6)]
    for x in ths:
        x.start()
    for x in ths:
        x.join()
    c = Counter(results)
    assert c.get(200) == 1, f"并发审批应恰 1 个成功，实际 {dict(c)}"
    print(f"[LOCK] 并发审批 {dict(c)} [OK]（1 成功 + 5 冲突）")

    print("\n=== 全部场景通过 ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
