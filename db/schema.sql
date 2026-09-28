-- SQLite schema for audit trail of investment decision tracking.
-- Phase 2 — AI-Orchestrated Equity Research & Risk Simulation Platform.
--
-- Every agent invocation generates an audit record. All records reference
-- a single run_id across the entire pipeline.
--
-- Required fields (non-negotiable, source of truth):
--     id INTEGER PRIMARY KEY
--     run_id TEXT
--     agent_name TEXT
--     timestamp TEXT
--     input_json TEXT
--     output_json TEXT
--     human_approval_status TEXT  -- 'pending' | 'approved' | 'rejected' | 'n/a'
--     approved_by TEXT
--     approved_at TEXT
--
-- The table must always contain these fields. Additional fields may be added
-- if necessary, but the required fields must never be removed.
--
-- Approval status values (must match specification):
--     'pending'     — approval has not yet been given
--     'approved'    — explicit human approval granted
--     'rejected'    — human rejection (pipeline terminates)
--     'n/a'         — not applicable (no approval relevant)

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY,
    run_id TEXT NOT NULL,
    agent_name TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    input_json TEXT,
    output_json TEXT,
    human_approval_status TEXT NOT NULL DEFAULT 'n/a',
    approved_by TEXT,
    approved_at TEXT
);