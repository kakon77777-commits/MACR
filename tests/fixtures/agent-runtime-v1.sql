PRAGMA foreign_keys = ON;

CREATE TABLE schema_meta (
    component TEXT PRIMARY KEY,
    version INTEGER NOT NULL CHECK(version >= 1)
);
INSERT INTO schema_meta(component, version) VALUES ('agent_runtime', 1);

CREATE TABLE agent_runs (
    agent_run_id TEXT PRIMARY KEY,
    subject_digest TEXT NOT NULL,
    agent_ref TEXT NOT NULL,
    initial_header_json TEXT NOT NULL,
    state TEXT NOT NULL CHECK(state IN (
        'created', 'admitted', 'active', 'waiting', 'suspended',
        'waking', 'blocked', 'reconciliation_required', 'completed',
        'failed', 'cancelled'
    )),
    state_revision INTEGER NOT NULL CHECK(state_revision >= 1),
    epoch INTEGER NOT NULL CHECK(epoch >= 0),
    goal_ref TEXT NOT NULL,
    authority_ref TEXT NOT NULL,
    budget_ref TEXT NOT NULL,
    semantic_state_ref TEXT,
    active_plan_ref TEXT,
    latest_checkpoint_ref TEXT,
    parent_agent_run_id TEXT,
    delegation_ref TEXT,
    state_digest TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CHECK(
        (parent_agent_run_id IS NULL AND delegation_ref IS NULL)
        OR
        (parent_agent_run_id IS NOT NULL AND delegation_ref IS NOT NULL)
    )
);

CREATE TABLE agent_events (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    agent_run_id TEXT NOT NULL,
    epoch INTEGER NOT NULL CHECK(epoch >= 0),
    before_revision INTEGER NOT NULL CHECK(before_revision >= 0),
    after_revision INTEGER NOT NULL CHECK(after_revision >= 1),
    event_type TEXT NOT NULL CHECK(event_type IN (
        'agent.run_created', 'agent.run_admitted',
        'agent.owner_acquired', 'agent.run_activated', 'agent.blocked',
        'agent.completed', 'agent.failed', 'agent.cancelled'
    )),
    payload_json TEXT NOT NULL,
    payload_digest TEXT NOT NULL,
    state_digest_after TEXT NOT NULL,
    created_at TEXT NOT NULL,
    CHECK(after_revision = before_revision + 1),
    UNIQUE(agent_run_id, after_revision)
);
CREATE INDEX agent_events_by_run ON agent_events(agent_run_id, sequence);
