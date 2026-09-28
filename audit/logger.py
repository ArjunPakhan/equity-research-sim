"""
Audit Logger — SQLite audit trail for investment decision tracking.

Every agent invocation generates an audit record. All records reference a
single run_id across the entire pipeline.

Required fields (from master specification):
    - id INTEGER PRIMARY KEY
    - run_id TEXT
    - agent_name TEXT
    - timestamp TEXT
    - input_json TEXT
    - output_json TEXT
    - human_approval_status TEXT  -- 'pending' | 'approved' | 'rejected' | 'n/a'
    - approved_by TEXT
    - approved_at TEXT

Useful additional fields may be added if necessary, but the required fields
must always be present.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Union

logger = logging.getLogger(__name__)

# Approval statuses (must match specification)
APPROVAL_PENDING = "pending"
APPROVAL_APPROVED = "approved"
APPROVAL_REJECTED = "rejected"
APPROVAL_N_A = "n/a"

# Database path
DEFAULT_DB_PATH = "audit.db"


def initialize_database(db_path: str = DEFAULT_DB_PATH) -> str:
    """
    Initialize the SQLite audit database.

    Creates the audit_log table if it does not exist and generates a new
    run_id for the pipeline.

    Args:
        db_path: Path to SQLite database file

    Returns:
        The generated run_id
    """
    run_id = datetime.now(timezone.utc).strftime("run_%Y%m%d_%H%M%S_%f")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY,
            run_id TEXT,
            agent_name TEXT,
            timestamp TEXT,
            input_json TEXT,
            output_json TEXT,
            human_approval_status TEXT,
            approved_by TEXT,
            approved_at TEXT
        )
    """)

    # Insert an initial record with run_id and pending status
    timestamp = datetime.now(timezone.utc).isoformat()
    cursor.execute("""
        INSERT INTO audit_log (run_id, agent_name, timestamp, human_approval_status,
                              approved_by, approved_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        run_id,
        "pipeline_initialization",
        timestamp,
        APPROVAL_PENDING,
        "system",
        timestamp,
    ))

    conn.commit()
    conn.close()
    logger.info(f"Audit database initialized: {db_path}, run_id: {run_id}")
    return run_id


def log_agent_call(
    db_path: str,
    run_id: str,
    agent_name: str,
    input_data: Optional[Dict[str, Any]] = None,
    output_data: Optional[Dict[str, Any]] = None,
    human_approval_status: Optional[str] = None,
    approved_by: Optional[str] = None,
) -> None:
    """
    Log an agent call to the audit database.

    Args:
        db_path: Path to SQLite database file
        run_id: Unique pipeline run identifier
        agent_name: Name of the agent that was called
        input_data: Input JSON dictionary (optional)
        output_data: Output JSON dictionary (optional)
        human_approval_status: 'pending' | 'approved' | 'rejected' | 'n/a' (optional)
        approved_by: Name or ID of the approver (optional)
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    timestamp = datetime.now(timezone.utc).isoformat()

    # Serialize input/output to JSON safely
    input_json = json.dumps(input_data) if input_data is not None else None
    output_json = json.dumps(output_data) if output_data is not None else None

    # Ensure approval status is one of the valid values
    if human_approval_status is not None:
        if human_approval_status not in (
                APPROVAL_PENDING, APPROVAL_APPROVED, APPROVAL_REJECTED, APPROVAL_N_A):
            human_approval_status = APPROVAL_N_A

    cursor.execute("""
        INSERT INTO audit_log
        (run_id, agent_name, timestamp, input_json, output_json,
         human_approval_status, approved_by, approved_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        run_id,
        agent_name,
        timestamp,
        input_json,
        output_json,
        human_approval_status,
        approved_by,
        timestamp if human_approval_status == APPROVAL_APPROVED else None,
    ))

    conn.commit()
    conn.close()

    logger.debug(f"Audit logged: {agent_name} for run {run_id}")


def get_audit_records(
    db_path: str,
    run_id: str = None,
    agent_name: str = None,
) -> list:
    """
    Retrieve audit records from the database.

    Args:
        db_path: Path to SQLite database file
        run_id: Filter by run_id (optional)
        agent_name: Filter by agent_name (optional)

    Returns:
        List of audit record dictionaries
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    query = "SELECT * FROM audit_log WHERE 1=1"
    params = []

    if run_id:
        query += " AND run_id = ?"
        params.append(run_id)

    if agent_name:
        query += " AND agent_name = ?"
        params.append(agent_name)

    cursor.execute(query, params)
    columns = [desc[0] for desc in cursor.description]
    records = []

    for row in cursor.fetchall():
        record = dict(zip(columns, row))
        records.append(record)

    conn.close()
    return records


def get_run_summary(db_path: str, run_id: str) -> Optional[Dict[str, Any]]:
    """
    Get a summary of all audit records for a given run_id.

    Args:
        db_path: Path to SQLite database file
        run_id: The run identifier

    Returns:
        Dictionary with summary information, or None if run_id not found
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT agent_name, human_approval_status, timestamp,
               approved_by, approved_at
        FROM audit_log
        WHERE run_id = ?
        ORDER BY id ASC
    """, (run_id,))

    rows = cursor.fetchall()
    conn.close()

    if not rows:
        return None

    summary = {
        "run_id": run_id,
        "total_records": len(rows),
        "agents": [],
        "approval_sequence": [],
    }

    for row in rows:
        agent_name = row[0]
        approval_status = row[1]
        timestamp = row[2]
        approved_by = row[3]
        approved_at = row[4]

        summary["agents"].append({
            "agent": agent_name,
            "status": approval_status,
            "timestamp": timestamp,
            "approved_by": approved_by,
            "approved_at": approved_at,
        })

        summary["approval_sequence"].append({
            "agent": agent_name,
            "status": approval_status,
            "at": timestamp,
            "by": approved_by,
        })

    return summary


if __name__ == "__main__":
    # Quick test
    import sys
    sys.path.insert(0, str(__file__).rsplit("\\", 2)[0])

    db_path = "test_audit.db"
    run_id = initialize_database(db_path)

    # Simulate logging a few agent calls
    log_agent_call(db_path, run_id, "research_agent",
                   input_data={"ticker": "RELIANCE"},
                   output_data={"trend": "bullish", "key_levels": [2500, 2600]},
                   human_approval_status="pending")

    log_agent_call(db_path, run_id, "risk_agent",
                   input_data={"run_id": run_id},
                   output_data={"checks_passed": True, "position_size": 10.0},
                   human_approval_status="approved")

    # Print summary
    summary = get_run_summary(db_path, run_id)
    if summary:
        print(f"Run summary for {summary['run_id']}:")
        print(f"  Total records: {summary['total_records']}")
        for agent in summary['agents']:
            print(f"  - {agent['agent']}: {agent['status']} at {agent['timestamp'][:16]}")

    # Clean up test database
    import os
    os.remove(db_path)