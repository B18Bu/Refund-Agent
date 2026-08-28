#!/usr/bin/env python3
"""可复跑 OCR 批量验证脚本。

脚本只创建远端工单，不删除任何 API 业务数据；--cleanup 仅清理本脚本生成的本地产物。
低置信样本受 PaddleOCR 版本、模型和运行环境影响，不能保证稳定低于阈值，正式批量运行前请先用小样本校准。
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import error, request

try:
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
except ImportError:  # pragma: no cover - 给未安装可选运行依赖时的清晰提示
    Image = ImageDraw = ImageFilter = ImageFont = None


SCRIPT_DIR = Path(__file__).resolve().parent
ARTIFACT_ROOT = SCRIPT_DIR / "ocr_suspension_artifacts"
DEFAULT_USERNAME = "customer_service_01"
DEFAULT_PASSWORD = ""
THRESHOLD = 0.6
TERMINAL_STATUSES = {"COMPLETED", "FAILED", "AUTO_REFUNDED"}


class ApiError(RuntimeError):
    """HTTP 或响应格式错误。"""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False).encode("utf-8")


def http_json(
    base_url: str,
    method: str,
    path: str,
    *,
    payload: Any = None,
    token: str | None = None,
    headers: dict[str, str] | None = None,
    timeout: float,
) -> tuple[int, Any]:
    body = json_bytes(payload) if payload is not None else None
    req = request.Request(base_url.rstrip("/") + path, data=body, method=method)
    if payload is not None:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    for name, value in (headers or {}).items():
        req.add_header(name, value)
    try:
        with request.urlopen(req, timeout=timeout) as response:
            raw = response.read()
            return response.status, json.loads(raw.decode("utf-8")) if raw else None
    except error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            detail = json.loads(raw)
        except json.JSONDecodeError:
            detail = raw
        raise ApiError(f"HTTP {exc.code} {path}: {detail}") from exc
    except (error.URLError, TimeoutError, OSError) as exc:
        raise ApiError(f"请求 {path} 失败：{exc}") from exc


def multipart_body(fields: dict[str, str], file_field: str, filename: str, content: bytes) -> tuple[bytes, str]:
    boundary = f"----ocr-e2e-{uuid.uuid4().hex}"
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.extend(
            [
                f"--{boundary}\r\n".encode(),
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
                value.encode("utf-8"),
                b"\r\n",
            ]
        )
    chunks.extend(
        [
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="{file_field}"; filename="{filename}"\r\n'.encode(),
            b"Content-Type: image/png\r\n\r\n",
            content,
            b"\r\n",
            f"--{boundary}--\r\n".encode(),
        ]
    )
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def post_ticket_with_file(
    base_url: str,
    token: str,
    image_path: Path,
    amount: float,
    idempotency_key: str,
    timeout: float,
) -> tuple[int, Any]:
    content = image_path.read_bytes()
    body, content_type = multipart_body({"amount": str(amount)}, "files", image_path.name, content)
    req = request.Request(base_url.rstrip("/") + "/api/tickets/with-files", data=body, method="POST")
    req.add_header("Content-Type", content_type)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("X-Idempotency-Key", idempotency_key)
    try:
        with request.urlopen(req, timeout=timeout) as response:
            raw = response.read()
            return response.status, json.loads(raw.decode("utf-8"))
    except error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        raise ApiError(f"HTTP {exc.code} /api/tickets/with-files: {raw}") from exc
    except (error.URLError, TimeoutError, OSError) as exc:
        raise ApiError(f"提交图片失败：{exc}") from exc


def load_font(size: int):
    if ImageFont is None:
        raise RuntimeError("生成 PNG 需要 Pillow；请按 backend/requirements.txt 安装依赖")
    for candidate in ("C:/Windows/Fonts/msyh.ttc", "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"):
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    return ImageFont.load_default()


def make_sample(path: Path, sample_class: str, index: int, rng: random.Random) -> None:
    """生成可被 Pillow 打开的 RGB PNG；不依赖外部图片或网络资源。"""
    if Image is None:
        raise RuntimeError("生成 PNG 需要 Pillow；请按 backend/requirements.txt 安装依赖")
    width, height = 900, 520
    image = Image.new("RGB", (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    label = f"退款凭证 {index:04d}"
    amount = f"金额 {rng.randint(80, 299)}.00 元"
    if sample_class == "baseline_clear":
        font = load_font(48)
        draw.rectangle((30, 30, width - 30, height - 30), outline=(20, 20, 20), width=5)
        draw.text((80, 150), label, fill=(0, 0, 0), font=font)
        draw.text((80, 250), amount, fill=(0, 0, 0), font=font)
    elif sample_class == "low_contrast_small_text":
        font = load_font(18)
        draw.text((100, 210), label, fill=(190, 190, 190), font=font)
        draw.text((100, 245), amount, fill=(202, 202, 202), font=font)
        draw.line((50, 430, 850, 430), fill=(225, 225, 225), width=2)
    else:  # occluded_blurred_or_blank：交替生成遮挡、模糊和无文字样本
        if index % 3 == 0:
            draw.rectangle((45, 45, 855, 475), fill=(245, 245, 245), outline=(35, 35, 35), width=3)
            draw.rectangle((260, 120, 700, 365), fill=(110, 110, 110))
        else:
            font = load_font(28)
            draw.text((80, 170), label, fill=(10, 10, 10), font=font)
            draw.text((80, 240), amount, fill=(10, 10, 10), font=font)
            draw.rectangle((300, 120, 780, 330), fill=(255, 255, 255))
            image = image.filter(ImageFilter.GaussianBlur(radius=5.0))
    image.save(path, format="PNG")


def proportional_counts(total: int) -> dict[str, int]:
    weights = {"baseline_clear": 20, "low_contrast_small_text": 40, "occluded_blurred_or_blank": 40}
    raw = {name: total * weight / 100 for name, weight in weights.items()}
    counts = {name: math.floor(value) for name, value in raw.items()}
    remainder = total - sum(counts.values())
    order = sorted(weights, key=lambda name: (raw[name] - counts[name], weights[name]), reverse=True)
    for name in order[:remainder]:
        counts[name] += 1
    return counts


def expected_range(sample_class: str) -> dict[str, Any]:
    if sample_class == "baseline_clear":
        return {"ocr_confidence": ">= 0.6（仅观察，不预设成功终态）", "note": "输出实际终态"}
    return {"ocr_confidence": "< 0.6", "status": "SUSPENDED", "outcome": "PENDING"}


def poll_ticket(base_url: str, token: str, ticket_id: int, timeout: float, interval: float) -> tuple[dict[str, Any] | None, str]:
    deadline = time.monotonic() + timeout
    last: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        try:
            _, last = http_json(base_url, "GET", f"/api/tickets/{ticket_id}", token=token, timeout=timeout)
        except ApiError as exc:
            return last, f"DETAIL_ERROR: {exc}"
        status = str(last.get("status", ""))
        outcome = str(last.get("outcome", last.get("decision", "")))
        if status in TERMINAL_STATUSES or status == "SUSPENDED" or outcome in {"FAILED", "AUTO_REFUNDED"}:
            return last, "OBSERVED_TERMINAL"
        time.sleep(interval)
    return last, "TIMEOUT"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="批量验证 OCR 低置信挂起行为（不删除远端数据）")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--count", type=int, default=100)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--timeout", type=float, default=120.0, help="单工单详情轮询秒数")
    parser.add_argument("--poll-interval", type=float, default=2.0)
    parser.add_argument("--keep-artifacts", action="store_true", help="保留本次本地 PNG 与 manifest")
    parser.add_argument("--cleanup", action="store_true", help="结束时清理本次脚本生成的本地 PNG 与 manifest")
    parser.add_argument("--username", default=DEFAULT_USERNAME, help="专用客户账号")
    parser.add_argument(
        "--password",
        default=os.environ.get("OCR_E2E_PASSWORD", DEFAULT_PASSWORD),
        help="专用客户密码（默认读取 OCR_E2E_PASSWORD 环境变量）",
    )
    args = parser.parse_args()
    if args.count < 1 or args.timeout <= 0 or args.poll_interval <= 0:
        parser.error("--count、--timeout、--poll-interval 必须为正数")
    return args


def write_manifest(path: Path, manifest: dict[str, Any]) -> None:
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    args = parse_args()
    run_id = args.run_id or datetime.now().strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:8]
    run_dir = ARTIFACT_ROOT / run_id
    manifest_path = run_dir / "manifest.json"
    rng = random.Random(args.seed)
    counts = proportional_counts(args.count)
    manifest: dict[str, Any] = {
        "run_id": run_id,
        "base_url": args.base_url,
        "seed": args.seed,
        "count": args.count,
        "category_counts": counts,
        "threshold": THRESHOLD,
        "ocr_calibration_note": "低置信样本受不同 PaddleOCR 版本、模型和运行环境影响，不能保证 OCR<0.6；正式批量运行前请先小样本校准。",
        "records": [],
        "started_at": utc_now(),
    }

    # 健康检查失败时不登录、不生成样本、不写远端数据。
    try:
        status, health = http_json(args.base_url, "GET", "/healthz", timeout=args.timeout)
    except ApiError as exc:
        print(f"[未运行] API 不可用，未登录、未生成样本、未写入远端数据：{exc}")
        print("[验证] 可执行 python -m py_compile scripts/ocr_suspension_e2e.py")
        return 0
    if status != 200 or not isinstance(health, dict) or health.get("status") != "ok":
        print(f"[未运行] /healthz 未返回 status=ok：HTTP {status} {health!r}")
        return 0

    if Image is None:
        print("[失败] 当前 Python 未安装 Pillow，无法生成合法 PNG；未登录、未写入远端数据。", file=sys.stderr)
        return 2
    run_dir.mkdir(parents=True, exist_ok=True)
    try:
        _, login = http_json(
            args.base_url,
            "POST",
            "/api/auth/login",
            payload={"username": args.username, "password": args.password},
            timeout=args.timeout,
        )
        token = login["access_token"]
    except (ApiError, KeyError, TypeError) as exc:
        print(f"[失败] 健康检查通过但登录失败，未提交工单：{exc}", file=sys.stderr)
        return 2

    print(f"[开始] run_id={run_id} count={args.count} categories={counts}")
    manifest["authenticated_at"] = utc_now()
    index = 0
    for sample_class, class_count in counts.items():
        for _ in range(class_count):
            index += 1
            image_path = run_dir / f"{index:04d}_{sample_class}.png"
            record: dict[str, Any] = {
                "sample_class": sample_class,
                "ticket_id": None,
                "submitted_at": None,
                "expected_range": expected_range(sample_class),
                "final_detail": None,
                "verdict": "NOT_SUBMITTED",
                "image": str(image_path.relative_to(ARTIFACT_ROOT)),
            }
            try:
                make_sample(image_path, sample_class, index, rng)
                submitted = utc_now()
                _, created = post_ticket_with_file(
                    args.base_url,
                    token,
                    image_path,
                    amount=128.0,
                    idempotency_key=f"ocr-e2e-{run_id}-{index:04d}-{uuid.uuid4().hex}",
                    timeout=args.timeout,
                )
                ticket_id = int(created["ticket_id"])
                record["ticket_id"] = ticket_id
                record["submitted_at"] = submitted
                detail, poll_result = poll_ticket(
                    args.base_url, token, ticket_id, args.timeout, args.poll_interval
                )
                record["final_detail"] = detail
                record["poll_result"] = poll_result
                if sample_class == "baseline_clear":
                    record["verdict"] = "OBSERVED" if detail else "FAIL"
                else:
                    record["verdict"] = (
                        "PASS"
                        if detail
                        and detail.get("ocr_confidence") is not None
                        and float(detail["ocr_confidence"]) < THRESHOLD
                        and detail.get("status") == "SUSPENDED"
                        and detail.get("outcome", detail.get("decision")) == "PENDING"
                        else "FAIL"
                    )
            except (ApiError, OSError, RuntimeError, KeyError, TypeError, ValueError) as exc:
                record["error"] = str(exc)
                record["verdict"] = "FAIL"
            manifest["records"].append(record)
            write_manifest(manifest_path, manifest)
            print(
                f"[{index}/{args.count}] {sample_class} ticket={record['ticket_id']} "
                f"verdict={record['verdict']}"
            )

    manifest["finished_at"] = utc_now()
    write_manifest(manifest_path, manifest)
    low_records = [r for r in manifest["records"] if r["sample_class"] != "baseline_clear"]
    passed = sum(r["verdict"] == "PASS" for r in low_records)
    failed = sum(r["verdict"] == "FAIL" for r in manifest["records"])
    print("\n=== OCR 批量验证汇总 ===")
    print(f"run_id: {run_id}")
    print(f"总数: {len(manifest['records'])}，低质严格通过: {passed}/{len(low_records)}，失败: {failed}")
    print("基线组不笼统判定成功，仅记录实际终态；低质组必须同时满足 OCR<0.6、SUSPENDED、PENDING。")
    print(f"manifest: {manifest_path}")
    print("注意：低置信效果受 PaddleOCR 版本/模型/环境影响，需先小样本校准。")

    if args.cleanup and not args.keep_artifacts:
        for child in run_dir.iterdir():
            child.unlink()
        run_dir.rmdir()
        print(f"[cleanup] 已清理本地产物：{run_dir}")
    elif args.keep_artifacts:
        print(f"[保留] 本地产物：{run_dir}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
