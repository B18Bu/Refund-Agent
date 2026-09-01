export type SecurityEvent = {
  ticket_ref: string
  created_at: string | null
  risk: number
  flags: string[]
  outcome: string
}

export type Report<T> = { available: boolean; generated_at?: string } & Partial<T>

export type SecurityGovernanceSummary = {
  generated_at: string
  runtime: { pending_human_review: number; recent_events: SecurityEvent[] }
  red_blue: Report<{
    attack_count: number
    legitimate_count: number
    block_rate: number
    false_positive_block_rate: number
    categories: { category: string; sample_count: number; block_rate: number }[]
  }>
  dlp: Report<{
    sample_count: number
    missed_count: number
    false_positive_count: number
    accuracy: number
    acceptance_status: string
    ner_status: string
  }>
  audit: Report<{ status: string; finding_counts: Record<string, number> }>
  gaps: { key: string; title: string; description: string; status: string }[]
}
