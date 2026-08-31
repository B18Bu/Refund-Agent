export type MeasurementType = 'actual' | 'estimated' | 'mixed'

export type EvaluationRecord = {
  id: number
  ticket_id: number
  run_id: string
  prompt_version: string
  provider: string
  measurement_type: MeasurementType
  baseline_input_tokens: number | null
  current_input_tokens: number | null
  current_output_tokens: number | null
  current_total_tokens: number | null
  saved_tokens: number | null
  reduction_ratio: number | null
  correctness_score: number | null
  safety_score: number | null
  explainability_score: number | null
  evaluation_status: string
  latency_breakdown: Record<string, number>
  decision_route: string | null
  reason_summary: string | null
  error_code: string | null
  created_at: string | null
}

export type EvaluationTrend = {
  date: string
  baseline_input_tokens: number | null
  current_input_tokens: number | null
  count: number
}

export type EvaluationSummary = {
  evaluation_count: number
  avg_baseline_input_tokens: number | null
  avg_current_input_tokens: number | null
  avg_saved_tokens: number | null
  avg_reduction_ratio: number | null
  average_scores: {
    correctness: number | null
    safety: number | null
    explainability: number | null
  }
  data_completeness: { token_records: number; score_records: number }
  measurement_types: MeasurementType[]
  trend: EvaluationTrend[]
  recent: EvaluationRecord[]
  golden: {
    available: boolean
    case_count?: number
    passed?: boolean
    score?: number
    max_score?: number
  }
}
