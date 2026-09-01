# A/B 成本对比报告（纯 LLM vs 双层混合流）

- 时间：2026-08-31T14:10:18+00:00，provider：mock，measurement：estimated
- 样本数：100

| 方案 | Token 消耗 | 平均 TTFT(ms) | 意图准确率 |
| --- | --- | --- | --- |
| 纯 LLM | 4944 | 1.95 | 93.0% |
| 双层混合流 | 2476 | 0.97 | 100.0% |

- Token 降低率：49.9%（目标 ≥40%，结果：达标）
- 强信号跳过 LLM 样本数：50

## 样本明细

| case_id | 期望意图 | 纯 LLM 预测 | 双层预测 | 分流 |
| --- | --- | --- | --- | --- |
| I001 | malicious | malicious | malicious | strong_signal |
| I002 | malicious | malicious | malicious | strong_signal |
| I003 | malicious | malicious | malicious | strong_signal |
| I004 | malicious | malicious | malicious | strong_signal |
| I005 | malicious | general | malicious | strong_signal |
| I006 | malicious | refund_request | malicious | strong_signal |
| I007 | malicious | malicious | malicious | strong_signal |
| I008 | malicious | malicious | malicious | strong_signal |
| I009 | malicious | malicious | malicious | strong_signal |
| I010 | malicious | malicious | malicious | strong_signal |
| I011 | malicious | malicious | malicious | strong_signal |
| I012 | malicious | malicious | malicious | strong_signal |
| I013 | malicious | malicious | malicious | strong_signal |
| I014 | malicious | refund_request | malicious | strong_signal |
| I015 | malicious | malicious | malicious | strong_signal |
| I016 | malicious | malicious | malicious | strong_signal |
| I017 | malicious | refund_request | malicious | strong_signal |
| I018 | malicious | malicious | malicious | strong_signal |
| I019 | malicious | malicious | malicious | strong_signal |
| I020 | malicious | malicious | malicious | strong_signal |
| I021 | malicious | malicious | malicious | strong_signal |
| I022 | malicious | malicious | malicious | strong_signal |
| I023 | malicious | general | malicious | strong_signal |
| I024 | malicious | malicious | malicious | strong_signal |
| I025 | malicious | malicious | malicious | strong_signal |
| I026 | malicious | malicious | malicious | strong_signal |
| I027 | malicious | malicious | malicious | strong_signal |
| I028 | malicious | malicious | malicious | strong_signal |
| I029 | malicious | malicious | malicious | strong_signal |
| I030 | malicious | refund_request | malicious | strong_signal |
| I031 | malicious | malicious | malicious | strong_signal |
| I032 | malicious | malicious | malicious | strong_signal |
| I033 | malicious | malicious | malicious | strong_signal |
| I034 | malicious | malicious | malicious | strong_signal |
| I035 | malicious | refund_request | malicious | strong_signal |
| I036 | malicious | malicious | malicious | strong_signal |
| I037 | malicious | malicious | malicious | strong_signal |
| I038 | malicious | malicious | malicious | strong_signal |
| I039 | malicious | malicious | malicious | strong_signal |
| I040 | malicious | malicious | malicious | strong_signal |
| I041 | malicious | malicious | malicious | strong_signal |
| I042 | malicious | malicious | malicious | strong_signal |
| I043 | malicious | malicious | malicious | strong_signal |
| I044 | malicious | malicious | malicious | strong_signal |
| I045 | malicious | malicious | malicious | strong_signal |
| I046 | malicious | malicious | malicious | strong_signal |
| I047 | malicious | malicious | malicious | strong_signal |
| I048 | malicious | malicious | malicious | strong_signal |
| I049 | malicious | malicious | malicious | strong_signal |
| I050 | malicious | malicious | malicious | strong_signal |
| I051 | refund_request | refund_request | refund_request | llm_judge |
| I052 | refund_request | refund_request | refund_request | llm_judge |
| I053 | refund_request | refund_request | refund_request | llm_judge |
| I054 | refund_request | refund_request | refund_request | llm_judge |
| I055 | refund_request | refund_request | refund_request | llm_judge |
| I056 | refund_request | refund_request | refund_request | llm_judge |
| I057 | refund_request | refund_request | refund_request | llm_judge |
| I058 | refund_request | refund_request | refund_request | llm_judge |
| I059 | refund_request | refund_request | refund_request | llm_judge |
| I060 | refund_request | refund_request | refund_request | llm_judge |
| I061 | refund_request | refund_request | refund_request | llm_judge |
| I062 | refund_request | refund_request | refund_request | llm_judge |
| I063 | refund_request | refund_request | refund_request | llm_judge |
| I064 | refund_request | refund_request | refund_request | llm_judge |
| I065 | refund_request | refund_request | refund_request | llm_judge |
| I066 | refund_request | refund_request | refund_request | llm_judge |
| I067 | refund_request | refund_request | refund_request | llm_judge |
| I068 | refund_request | refund_request | refund_request | llm_judge |
| I069 | refund_request | refund_request | refund_request | llm_judge |
| I070 | refund_request | refund_request | refund_request | llm_judge |
| I071 | complaint | complaint | complaint | llm_judge |
| I072 | complaint | complaint | complaint | llm_judge |
| I073 | complaint | complaint | complaint | llm_judge |
| I074 | complaint | complaint | complaint | llm_judge |
| I075 | complaint | complaint | complaint | llm_judge |
| I076 | complaint | complaint | complaint | llm_judge |
| I077 | complaint | complaint | complaint | llm_judge |
| I078 | complaint | complaint | complaint | llm_judge |
| I079 | complaint | complaint | complaint | llm_judge |
| I080 | complaint | complaint | complaint | llm_judge |
| I081 | complaint | complaint | complaint | llm_judge |
| I082 | complaint | complaint | complaint | llm_judge |
| I083 | complaint | complaint | complaint | llm_judge |
| I084 | complaint | complaint | complaint | llm_judge |
| I085 | complaint | complaint | complaint | llm_judge |
| I086 | complaint | complaint | complaint | llm_judge |
| I087 | complaint | complaint | complaint | llm_judge |
| I088 | complaint | complaint | complaint | llm_judge |
| I089 | complaint | complaint | complaint | llm_judge |
| I090 | complaint | complaint | complaint | llm_judge |
| I091 | general | general | general | llm_judge |
| I092 | general | general | general | llm_judge |
| I093 | general | general | general | llm_judge |
| I094 | general | general | general | llm_judge |
| I095 | general | general | general | llm_judge |
| I096 | general | general | general | llm_judge |
| I097 | refund_request | refund_request | refund_request | llm_judge |
| I098 | refund_request | refund_request | refund_request | llm_judge |
| I099 | refund_request | refund_request | refund_request | llm_judge |
| I100 | general | general | general | llm_judge |
