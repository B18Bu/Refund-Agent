def test_optimized_prompt_is_at_least_thirty_percent_shorter():
    from app.agents.prompts import estimate_prompt_tokens, optimized_prompt, legacy_prompt

    baseline = estimate_prompt_tokens(legacy_prompt("退款金额：128\n凭证 OCR：清晰商品图"))
    optimized = estimate_prompt_tokens(optimized_prompt("退款金额：128\n凭证 OCR：清晰商品图"))

    assert optimized < baseline
    assert (baseline - optimized) / baseline >= 0.30

