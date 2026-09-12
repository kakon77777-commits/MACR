from __future__ import annotations

from ..database import AgentDatabase
from .errors import HostedAgentCellStateError


class HostedAgentCellSchema:
    SCHEMA_VERSION = 1

    def __init__(self, database: AgentDatabase) -> None:
        if not isinstance(database, AgentDatabase):
            raise ValueError("database must be an AgentDatabase")
        self.database = database
        self._initialize()

    def _initialize(self) -> None:
        connection = self.database.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            for statement in _SCHEMA_STATEMENTS:
                connection.execute(statement)
            row = connection.execute(
                "SELECT version FROM schema_meta WHERE component=?",
                ("hosted_agent_cell",),
            ).fetchone()
            if row is None:
                connection.execute(
                    "INSERT INTO schema_meta(component, version) VALUES (?, ?)",
                    ("hosted_agent_cell", self.SCHEMA_VERSION),
                )
            elif row["version"] != self.SCHEMA_VERSION:
                raise HostedAgentCellStateError(
                    "hosted Agent cell schema version is unsupported"
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()


_SCHEMA_STATEMENTS = (
    """CREATE TABLE IF NOT EXISTS hosted_agent_cells (
        agent_run_id TEXT PRIMARY KEY REFERENCES agent_runs(agent_run_id),
        cell_revision INTEGER NOT NULL CHECK(cell_revision >= 1),
        policy_json TEXT NOT NULL,
        policy_digest TEXT NOT NULL,
        semantic_request_json TEXT NOT NULL,
        semantic_request_digest TEXT NOT NULL,
        status TEXT NOT NULL CHECK(status IN (
            'ready', 'running', 'checkpointed', 'completion_pending',
            'completed', 'blocked', 'reconciliation_required'
        )),
        next_step INTEGER NOT NULL CHECK(next_step >= 1),
        provider_calls INTEGER NOT NULL CHECK(provider_calls >= 0),
        tool_calls INTEGER NOT NULL CHECK(tool_calls >= 0),
        active_wall_ms INTEGER NOT NULL CHECK(active_wall_ms >= 0),
        currency_cost_usd REAL NOT NULL CHECK(currency_cost_usd >= 0),
        latest_checkpoint_digest TEXT,
        candidate_run_id TEXT,
        final_capture_id TEXT,
        final_answer_digest TEXT,
        state_digest TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        CHECK(
            (candidate_run_id IS NULL AND final_capture_id IS NULL
             AND final_answer_digest IS NULL)
            OR
            (candidate_run_id IS NOT NULL AND final_capture_id IS NOT NULL
             AND final_answer_digest IS NOT NULL)
        )
    )""",
    """CREATE INDEX IF NOT EXISTS hosted_agent_cells_by_status
    ON hosted_agent_cells(status, agent_run_id)""",
    """CREATE TABLE IF NOT EXISTS hosted_agent_cell_events (
        sequence INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id TEXT NOT NULL UNIQUE,
        agent_run_id TEXT NOT NULL REFERENCES agent_runs(agent_run_id),
        cell_revision INTEGER NOT NULL CHECK(cell_revision >= 1),
        event_type TEXT NOT NULL CHECK(event_type IN (
            'cell.attached', 'cell.context_appended',
            'cell.model_dispatched', 'cell.model_completed',
            'cell.model_failed', 'cell.tool_admitted', 'cell.tool_denied',
            'cell.tool_claimed', 'cell.tool_completed', 'cell.checkpointed', 'cell.rehydrated',
            'cell.completion_intent', 'cell.completion_prepared',
            'cell.completed', 'cell.reconciliation_required'
        )),
        payload_json TEXT NOT NULL,
        payload_digest TEXT NOT NULL,
        prior_event_digest TEXT NOT NULL,
        state_after_json TEXT NOT NULL,
        state_digest_after TEXT NOT NULL,
        event_digest TEXT NOT NULL UNIQUE,
        created_at TEXT NOT NULL,
        UNIQUE(agent_run_id, cell_revision)
    )""",
    """CREATE INDEX IF NOT EXISTS hosted_agent_cell_events_by_run
    ON hosted_agent_cell_events(agent_run_id, cell_revision)""",
    """CREATE TABLE IF NOT EXISTS hosted_agent_blobs (
        agent_run_id TEXT NOT NULL REFERENCES agent_runs(agent_run_id),
        role TEXT NOT NULL CHECK(role IN (
            'context', 'projection', 'model_raw', 'model_decision',
            'tool_arguments', 'tool_result'
        )),
        sha256 TEXT NOT NULL,
        byte_count INTEGER NOT NULL CHECK(byte_count >= 0),
        blob_ref TEXT NOT NULL UNIQUE,
        reference_digest TEXT NOT NULL,
        created_at TEXT NOT NULL,
        PRIMARY KEY(agent_run_id, role, sha256)
    )""",
    """CREATE TABLE IF NOT EXISTS hosted_context_sections (
        sequence INTEGER PRIMARY KEY AUTOINCREMENT,
        section_id TEXT NOT NULL UNIQUE,
        agent_run_id TEXT NOT NULL REFERENCES agent_runs(agent_run_id),
        kind TEXT NOT NULL CHECK(kind IN (
            'operator_brief', 'project_fact', 'tool_result', 'tool_denial'
        )),
        blob_ref TEXT NOT NULL REFERENCES hosted_agent_blobs(blob_ref),
        body_digest TEXT NOT NULL,
        body_bytes INTEGER NOT NULL CHECK(body_bytes > 0),
        source_digest TEXT NOT NULL,
        section_digest TEXT NOT NULL UNIQUE,
        created_at TEXT NOT NULL
    )""",
    """CREATE INDEX IF NOT EXISTS hosted_context_sections_by_run
    ON hosted_context_sections(agent_run_id, sequence)""",
    """CREATE TABLE IF NOT EXISTS hosted_context_envelopes (
        envelope_digest TEXT PRIMARY KEY,
        agent_run_id TEXT NOT NULL REFERENCES agent_runs(agent_run_id),
        step_index INTEGER NOT NULL CHECK(step_index >= 1),
        agent_run_epoch INTEGER NOT NULL CHECK(agent_run_epoch >= 1),
        agent_state_revision INTEGER NOT NULL CHECK(agent_state_revision >= 1),
        semantic_projection_digest TEXT NOT NULL,
        policy_digest TEXT NOT NULL,
        tool_catalog_digest TEXT NOT NULL,
        causal_digest TEXT NOT NULL,
        blob_ref TEXT NOT NULL REFERENCES hosted_agent_blobs(blob_ref),
        byte_count INTEGER NOT NULL CHECK(byte_count > 0),
        created_at TEXT NOT NULL,
        UNIQUE(agent_run_id, step_index, envelope_digest)
    )""",
    """CREATE INDEX IF NOT EXISTS hosted_context_envelopes_by_run
    ON hosted_context_envelopes(agent_run_id, step_index, envelope_digest)""",
    """CREATE TABLE IF NOT EXISTS hosted_model_dispatches (
        provider_invocation_id TEXT PRIMARY KEY,
        agent_run_id TEXT NOT NULL REFERENCES agent_runs(agent_run_id),
        step_index INTEGER NOT NULL CHECK(step_index >= 1),
        request_json TEXT NOT NULL,
        request_digest TEXT NOT NULL UNIQUE,
        context_digest TEXT NOT NULL,
        dispatched_at TEXT NOT NULL,
        UNIQUE(agent_run_id, step_index)
    )""",
    """CREATE TABLE IF NOT EXISTS hosted_model_terminals (
        provider_invocation_id TEXT PRIMARY KEY
            REFERENCES hosted_model_dispatches(provider_invocation_id),
        terminal_state TEXT NOT NULL CHECK(terminal_state IN (
            'completed', 'failed', 'reconciliation_required'
        )),
        result_json TEXT,
        result_digest TEXT,
        raw_blob_ref TEXT REFERENCES hosted_agent_blobs(blob_ref),
        decision_blob_ref TEXT REFERENCES hosted_agent_blobs(blob_ref),
        currency_cost_usd REAL,
        duration_ms INTEGER NOT NULL CHECK(duration_ms >= 0),
        network_attempted INTEGER,
        response_received INTEGER,
        failure_code TEXT,
        failure_digest TEXT,
        terminal_at TEXT NOT NULL,
        CHECK(network_attempted IS NULL OR network_attempted IN (0, 1)),
        CHECK(response_received IS NULL OR response_received IN (0, 1)),
        CHECK(response_received IS NULL OR response_received=0 OR network_attempted=1),
        CHECK(
            (terminal_state='completed' AND result_json IS NOT NULL
             AND result_digest IS NOT NULL AND raw_blob_ref IS NOT NULL
             AND decision_blob_ref IS NOT NULL AND failure_code IS NULL
             AND failure_digest IS NULL)
            OR
            (terminal_state!='completed' AND result_json IS NULL
             AND result_digest IS NULL AND decision_blob_ref IS NULL
             AND failure_code IS NOT NULL AND failure_digest IS NOT NULL)
        )
    )""",
    """CREATE TABLE IF NOT EXISTS hosted_tool_requests (
        action_id TEXT PRIMARY KEY,
        agent_run_id TEXT NOT NULL REFERENCES agent_runs(agent_run_id),
        step_index INTEGER NOT NULL CHECK(step_index >= 1),
        model_request_digest TEXT NOT NULL UNIQUE,
        tool_id TEXT NOT NULL,
        arguments_blob_ref TEXT NOT NULL REFERENCES hosted_agent_blobs(blob_ref),
        arguments_digest TEXT NOT NULL,
        proposal_json TEXT,
        proposal_digest TEXT,
        admission_json TEXT,
        admission_digest TEXT,
        decision TEXT NOT NULL CHECK(decision IN ('admitted', 'denied')),
        reason_code TEXT,
        reason_digest TEXT,
        created_at TEXT NOT NULL,
        CHECK(
            (decision='admitted' AND proposal_json IS NOT NULL
             AND proposal_digest IS NOT NULL AND admission_json IS NOT NULL
             AND admission_digest IS NOT NULL AND reason_code IS NULL
             AND reason_digest IS NULL)
            OR
            (decision='denied' AND proposal_json IS NULL
             AND proposal_digest IS NULL AND admission_json IS NULL
             AND admission_digest IS NULL AND reason_code IS NOT NULL
             AND reason_digest IS NOT NULL)
        )
    )""",
    """CREATE INDEX IF NOT EXISTS hosted_tool_requests_by_run
    ON hosted_tool_requests(agent_run_id, step_index, action_id)""",
    """CREATE TABLE IF NOT EXISTS hosted_tool_results (
        action_id TEXT PRIMARY KEY REFERENCES hosted_tool_requests(action_id),
        result_ref_json TEXT NOT NULL,
        reference_digest TEXT NOT NULL,
        result_blob_ref TEXT REFERENCES hosted_agent_blobs(blob_ref),
        result_digest TEXT,
        result_bytes INTEGER,
        duration_ms INTEGER NOT NULL CHECK(duration_ms >= 0),
        status TEXT NOT NULL CHECK(status IN ('completed', 'failed')),
        observed_at TEXT NOT NULL,
        CHECK(
            (status='completed' AND result_blob_ref IS NOT NULL
             AND result_digest IS NOT NULL AND result_bytes IS NOT NULL)
            OR
            (status='failed' AND result_blob_ref IS NULL
             AND result_digest IS NULL AND result_bytes IS NULL)
        )
    )""",
    """CREATE TABLE IF NOT EXISTS hosted_tool_execution_claims (
        action_id TEXT PRIMARY KEY REFERENCES hosted_tool_requests(action_id),
        admission_digest TEXT NOT NULL,
        ownership_lease_id TEXT NOT NULL,
        ownership_fencing_token INTEGER NOT NULL CHECK(ownership_fencing_token >= 1),
        cell_state_digest TEXT NOT NULL,
        semantic_projection_digest TEXT NOT NULL,
        claim_digest TEXT NOT NULL UNIQUE,
        claimed_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS hosted_agent_checkpoints (
        checkpoint_id TEXT PRIMARY KEY,
        agent_run_id TEXT NOT NULL REFERENCES agent_runs(agent_run_id),
        cell_revision INTEGER NOT NULL CHECK(cell_revision >= 1),
        checkpoint_json TEXT NOT NULL,
        checkpoint_digest TEXT NOT NULL UNIQUE,
        cell_snapshot_json TEXT NOT NULL,
        cell_snapshot_digest TEXT NOT NULL,
        parent_checkpoint_digest TEXT,
        created_at TEXT NOT NULL,
        UNIQUE(agent_run_id, cell_revision)
    )""",
    """CREATE INDEX IF NOT EXISTS hosted_agent_checkpoints_by_run
    ON hosted_agent_checkpoints(agent_run_id, cell_revision)""",
    """CREATE TABLE IF NOT EXISTS hosted_agent_rehydrations (
        rehydration_id TEXT PRIMARY KEY,
        agent_run_id TEXT NOT NULL REFERENCES agent_runs(agent_run_id),
        cell_revision INTEGER NOT NULL CHECK(cell_revision >= 1),
        checkpoint_digest TEXT NOT NULL,
        previous_epoch INTEGER NOT NULL CHECK(previous_epoch >= 1),
        new_epoch INTEGER NOT NULL CHECK(new_epoch > previous_epoch),
        fencing_token INTEGER NOT NULL CHECK(fencing_token >= 1),
        receipt_digest TEXT NOT NULL UNIQUE,
        rehydrated_at TEXT NOT NULL,
        UNIQUE(agent_run_id, cell_revision)
    )""",
    """CREATE TABLE IF NOT EXISTS hosted_agent_completions (
        candidate_run_id TEXT PRIMARY KEY,
        agent_run_id TEXT NOT NULL UNIQUE REFERENCES agent_runs(agent_run_id),
        final_capture_id TEXT NOT NULL,
        final_answer_digest TEXT NOT NULL,
        decision_digest TEXT NOT NULL,
        evidence_refs_digest TEXT NOT NULL,
        prepared_at TEXT NOT NULL,
        finalized_at TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS hosted_agent_completion_intents (
        candidate_run_id TEXT PRIMARY KEY,
        agent_run_id TEXT NOT NULL UNIQUE REFERENCES agent_runs(agent_run_id),
        decision_digest TEXT NOT NULL,
        final_answer_digest TEXT NOT NULL,
        evidence_refs_json TEXT NOT NULL,
        evidence_refs_digest TEXT NOT NULL,
        intent_digest TEXT NOT NULL UNIQUE,
        created_at TEXT NOT NULL
    )""",
)
