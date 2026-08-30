"""输出 Prompt 优化前后的离线相对 Token 基线。"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.agents.prompts import estimate_prompt_tokens, legacy_prompt, optimized_prompt  # noqa: E402

material = "退款金额：128\n凭证 OCR：清晰商品图"
baseline = estimate_prompt_tokens(legacy_prompt(material))
optimized = estimate_prompt_tokens(optimized_prompt(material))
reduction = (baseline - optimized) / baseline
print({"baseline_tokens": baseline, "optimized_tokens": optimized, "reduction_ratio": round(reduction, 4), "measurement": "offline_relative_estimate"})
raise SystemExit(0 if reduction >= 0.30 else 1)

