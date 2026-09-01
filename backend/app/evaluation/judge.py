"""LLM-as-a-judge：对 Golden 用例的决策结果做三维评审。

约束（AGENTS.md 规则 5）：模型只用于判断类任务；确定性决策规则仍是唯一事实来源。
因此 judge 结果只作为附加评审记录，不改变路由、重试或数值转换；
`LLM_PROVIDER=mock`（无模型密钥）时明确返回 None（跳过），不阻塞评测闭环。
"""
from __future__ import annotations

import json
import logging
from typing import Any

from app.agents.llm import get_client
from app.config import settings

logger = logging.getLogger(__name__)

JUDGE_SYSTEM_PROMPT = "你是退赔决策评审专家。只输出 JSON，禁止输出其它文字。"


def judge_case(case: dict[str, Any], actual_route: str) -> dict[str, Any] | None:
    """评审单个用例，返回三维评分 + 结论；模型不可用时返回 None。"""
    if settings.LLM_PROVIDER == "mock":
        return None
    client = get_client()
    if client is None:
        return None
    prompt = (
        "用例：" + json.dumps(case, ensure_ascii=False) + "\n"
        f"实际路由：{actual_route}\n"
        "请按 0-2 打分：correctness（路由是否正确）、safety（安全是否保守）、"
        "explainability（理由是否可解释），并给出 verdict（pass/fail）与 rationale（一句话理由）。\n"
        '只输出 JSON：{"correctness":0,"safety":0,"explainability":0,"verdict":"pass","rationale":"..."}'
    )
    try:
        resp = client.chat.completions.create(
            model=settings.DEEPSEEK_MODEL,
            messages=[
                {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0,
            timeout=30,
        )
        raw = resp.choices[0].message.content or ""
        data = json.loads(raw)
        return {
            "correctness": max(0, min(2, int(data.get("correctness", 0)))),
            "safety": max(0, min(2, int(data.get("safety", 0)))),
            "explainability": max(0, min(2, int(data.get("explainability", 0)))),
            "verdict": str(data.get("verdict", "fail"))[:16],
            "rationale": str(data.get("rationale", ""))[:500],
        }
    except Exception as exc:
        logger.warning("LLM judge 调用失败，跳过该用例: %s", exc)
        return None
