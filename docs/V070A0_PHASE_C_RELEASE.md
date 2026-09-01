# MACR v0.7 Phase-C Alpha — 0.7.0a0 Release Record

Status: release candidate pending merged-main verification and `v0.7.0a0` tag

Date: 2026-09-01

## Exact accepted implementation base

```text
Phase C checkpoint commit  84a562fe58de8a279d427f6dd33ddc05410d1b1c
Phase C checkpoint tree    b0bbbc2210e50d47d6447d1e7bdf32c4aaa2e05f
release version            0.7.0a0
release label              MACR v0.7 Phase-C Alpha
target branch              main
target tag                 v0.7.0a0
```

The version/tag commit is intentionally later than the accepted implementation
base. The tag must identify the separately verified merged `main`; this record
does not make a self-referential release-commit claim.

## Why `a0`

The current checkpoint establishes the A-C foundation:

```text
Phase A  contract kernel
Phase B  AgentRun state kernel
Phase C  semantic working state
```

The canonical plan reserves the full bounded single-Agent MVP for later A-H
completion. Therefore `0.7.0a1` remains reserved. Stable `0.7.0` is not claimed.

Current stop boundary:

```text
Phase D      NOT STARTED
Agent loop   NOT IMPLEMENTED
Live use     NOT MEASURED
```

## Included

- all retained v0.6 Direct/delegated provider and accounting behavior;
- Agent runtime schema 2 and semantic schema 1 contracts;
- immutable semantic graphs and reconstructible head projection;
- per-Agent pinned semantic state;
- authority-free proposals and host-governed atomic commits;
- exact attach/commit receipts and idempotent persisted readback;
- shared-graph pinning, multiprocess CAS, tamper/rebuild controls;
- coherent bounded Goal-to-Plan context projection;
- D-drive isolated wheel reconstruction and Phase A/B/v0.6 compatibility gates.

## Excluded and NotMeasured

- Phase D verified observation, action execution, temporal continuation, closed
  loop, autonomous completion, or provider-generated Agent behavior;
- shared/default Agent database creation, migration, activation, encryption,
  backup, restore, or operator adoption;
- provider reachability, billing, quality, latency, live route, or token spend;
- Direct-to-Agent conversation transfer, automatic provider routing, retry, or
  fallback;
- deployment or service activation beyond source publication.

## Deferred Claude host compatibility

**Claude Code direct provider access** is deferred and NotMeasured. A later
subscription-client host adapter should let an authorized Claude Code session
use the same provider registry, model-local limits, authority/lease gates,
candidate separation, and accounting used by MACR for Grok, GLM, Google,
MiniMax, and Ollama/Qwythos.

This release does not implement that adapter. It must not read
`ANTHROPIC_API_KEY`, convert a Claude subscription into API billing, read Direct
conversations by default, or gain provider/fallback authority from semantic
content. `claude_subscription` remains disabled.

## Release gates

Before tagging and pushing:

```text
version surfaces and release tests
verify-v07-phase-c.ps1
verify-v07-phase-b.ps1
verify-v07-phase-a.ps1
verify-v06.ps1
merged-main exact verification
tag peel and remote main/tag readback
```

Every release gate remains offline: no credential read, provider call, shared
Agent state change, or live authority follows from the version/tag.
