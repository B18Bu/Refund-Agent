CREATE TABLE IF NOT EXISTS agent_evaluation_runs (
    id SERIAL PRIMARY KEY,
    ticket_id INTEGER NOT NULL REFERENCES tickets (id),
    run_id VARCHAR(128) NOT NULL,
    prompt_version VARCHAR(64) NOT NULL,
    provider VARCHAR(32) NOT NULL,
    measurement_type VARCHAR(16) NOT NULL,
    baseline_input_tokens INTEGER,
    current_input_tokens INTEGER,
    current_output_tokens INTEGER,
    current_total_tokens INTEGER,
    saved_tokens INTEGER,
    reduction_ratio NUMERIC(10, 6),
    correctness_score NUMERIC(3, 2),
    safety_score NUMERIC(3, 2),
    explainability_score NUMERIC(3, 2),
    evaluation_status VARCHAR(16) NOT NULL,
    latency_breakdown JSON NOT NULL DEFAULT '{}',
    decision_route VARCHAR(32),
    reason_summary TEXT,
    error_code VARCHAR(64),
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_agent_evaluation_runs_run_id
    ON agent_evaluation_runs (run_id);

CREATE INDEX IF NOT EXISTS ix_agent_evaluation_runs_ticket_id
    ON agent_evaluation_runs (ticket_id);
