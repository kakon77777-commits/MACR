# MACR v0.7 Phase A Checkpoint — Agent Contract Kernel

Status: implemented and offline-validated; Phase B not started

Date: 2026-08-31

## Exact subject

```text
baseline commit          d3ecaf16de66fb7df326253fbd09df3aa353b5f4
branch                   workbench/v0.7-agent-contract-kernel
source-frozen commit     b26a3ddba81a0fa45d93658fab9a254a56bf9d2c
source-frozen tree       8c0a91a02c73b7d1098f5be2daf7157e1cbfb05a
package version          0.6.0a1 (intentionally unchanged)
worktree before gates    clean
network activity         false
provider generation      false
Phase B started          false
```

The source-frozen subject is the last implementation and verification-infrastructure
commit before this checkpoint document. The checkpoint commit is verified separately
after it is created so the document does not make a self-referential commit claim.

## Delivered contract surface

Phase A introduces closed, immutable, digest-bound data contracts only. It does not
introduce an agent runtime, scheduler, planner, lifecycle engine, state store, database
migration, provider route, or Interaction Plane change.

Core support:

```text
src/macr_runtime/_v07_contracts.py
```

Contract families:

```text
src/macr_runtime/agent/contracts.py
src/macr_runtime/semantic/contracts.py
src/macr_runtime/observation/contracts.py
src/macr_runtime/action/contracts.py
src/macr_runtime/temporal/contracts.py
```

Their package `__init__.py` files expose the public types. `pyproject.toml` includes
the five schema package-data patterns.

The contract boundary includes:

- occurrence identity separate from subject identity;
- Goal, Budget, Semantic State, Plan, World State, existing AuthorizationReference,
  and reference-only Memory bindings in `AgentRunHeader`;
- semantic content identity separate from record/provenance identity, with typed
  unresolved, ambiguity, obligation, correction, resolution, and proposal-only patch
  records;
- raw observation separate from verified observation, with explicit scope, freshness,
  visibility, and re-observation bindings;
- action proposal, admission, command, provider attempt, receipt, verification, and
  reconciliation as distinct types;
- reference-only checkpoints plus declarative suspend, wake, resume, lease, and
  dependency records; wake data cannot encode an ACTIVE transition;
- deep freezing before digest construction so caller-owned nested containers cannot
  mutate an already identified record.

Artifact roles, semantic decisions, capability availability, memory references, raw
observations, wake events, and model-emitted fields do not construct authority.

## Schema identities

```text
urn:evemisslab:macr:agent-contracts:v1
  src/macr_runtime/agent/schemas/agent-contracts-v1.schema.json

urn:evemisslab:macr:semantic-contracts:v1
  src/macr_runtime/semantic/schemas/semantic-contracts-v1.schema.json

urn:evemisslab:macr:observation-contracts:v1
  src/macr_runtime/observation/schemas/observation-contracts-v1.schema.json

urn:evemisslab:macr:action-contracts:v1
  src/macr_runtime/action/schemas/action-contracts-v1.schema.json

urn:evemisslab:macr:temporal-contracts:v1
  src/macr_runtime/temporal/schemas/temporal-contracts-v1.schema.json
```

These schemas are interoperability descriptions for the Phase A contract surface.
They do not by themselves authorize actions or prove runtime enforcement.

## Test and gate evidence

Focused modules:

```text
tests/test_v07_contract_support.py
tests/test_agent_contracts.py
tests/test_semantic_contracts.py
tests/test_observation_contracts.py
tests/test_action_contracts.py
tests/test_temporal_contracts.py
tests/test_agent_contract_boundaries.py
tests/test_v07_phase_a_manifest.py
```

The machine-readable manifest is
`tests/gates/v07_phase_a_contract_manifest.json`. It contains 68 unique required
test IDs, including S0 negative boundaries. The wrapper is
`scripts/verify-v07-phase-a.ps1`.

Source-frozen Phase A wrapper result:

```text
command                  .\scripts\verify-v07-phase-a.ps1
exit                     0
focused tests            91 passed
required manifest IDs    68 discovered and unique
compileall               passed for src and tests
inherited verify.ps1     573 tests; OK; 2 existing Windows symlink skips
git diff --check         passed
tracked/untracked state  clean
doctor network activity  false
provider generation      false
summary schema           macr-v07-phase-a-summary/v1
```

Source-frozen complete v0.6 gate result:

```text
command                  .\scripts\verify-v06.ps1
exit                     0
complete tests           573 tests; OK; 2 existing Windows symlink skips
targeted tests           127 passed
network activity         false
provider generation      false
git clean                true
summary digest           1ed330453f63298af34ee98f2c3f39a2a8323d7a9d35d865ee4dcc3b3c5a3d13
schema fingerprint       43ca1e5e8cc0f75b4ac5de1821ce2f8b2d7d5632e7ad0a151910543dc396c0b5
```

The focused set is deliberately rerun inside inherited discovery; the counts above
are execution counts, not an assertion that 91 + 573 are distinct tests.

## Package smoke

`python -m pip wheel . --no-deps --no-build-isolation` completed without publishing.
The wheel was written under D-drive test state and had SHA-256:

```text
7ba574306cbd13b0c3dda46ff7ca2e4838bef754ca0638980901305832d000be
```

Its archive contains exactly these five Phase A schema members:

```text
macr_runtime/action/schemas/action-contracts-v1.schema.json
macr_runtime/agent/schemas/agent-contracts-v1.schema.json
macr_runtime/observation/schemas/observation-contracts-v1.schema.json
macr_runtime/semantic/schemas/semantic-contracts-v1.schema.json
macr_runtime/temporal/schemas/temporal-contracts-v1.schema.json
```

## Test-first implementation record

Each contract family began with a focused failing test for the absent interface,
then received the minimum implementation required for the focused and inherited gates.
The retained implementation sequence is:

```text
0dce6f4 feat(agent): add v0.7 contract support
4bcfd16 feat(agent): add AgentRun contract family
ea1ce2e feat(agent): add semantic envelope contracts
b130c4a feat(agent): add verified observation contracts
1934286 feat(agent): add governed action contracts
3120163 feat(agent): add temporal continuation contracts
d903c98 test(agent): enforce Phase A contract boundaries
b26a3dd test(agent): add Phase A verification gate
```

The two preceding documentation commits retain the field baseline and approved
implementation plan. No delegated agent or external provider authored or verified
this Phase A implementation.

## Deferred and NotMeasured

- NotMeasured: a running AgentRun lifecycle, durable agent state, scheduler, planner,
  runner, lease renewal, crash recovery, cross-machine coordination, or database
  migration;
- NotMeasured: live Grok, Qwythos/Ollama, GLM, Google, MiniMax, Codex, Claude Code,
  or any other provider integration, latency, billing, retention, or output quality;
- NotMeasured: provider-side network silence by packet capture. The recorded false
  values mean the offline gates invoked no provider path and doctor reported no
  network activity;
- NotMeasured: external semantic systems, EML-U implementation, NOVA integration,
  ISQL integration, or memory-body ingestion. `MemoryBindingRef` remains reference-only;
- NotMeasured: Direct Chat or Interaction Plane behavior, production migration,
  acceptance, merge, tag, release, deployment, adoption, push, or publication;
- Deferred to Phase B or later: runtime state transitions, durable storage, execution
  orchestration, wake evaluation, provider action execution, projection UI, and live
  integration acceptance.

No credential was read, no provider call occurred, no shared runtime was migrated,
and no wheel was published while producing this checkpoint.

## Verdict and stop boundary

```text
Phase A        IMPLEMENTED / OFFLINE VALIDATED
Phase B        NOT STARTED
Agent runtime  NOT IMPLEMENTED
Live use       NOT MEASURED / NOT AUTHORIZED BY THIS CHECKPOINT
```

The required Phase A stop is active. Work must not continue into Phase B from this
checkpoint without a separate operator direction and plan review.
