# MACR v0.6.0a0 Local Release Decision — 2026-08-30

Neo authorized updating, merging, and publishing the verified MACR v0.6 work.

## Release identity

```text
version              0.6.0a0
release tag          v0.6.0a0
integration base     feature/macr-v0.5-direct-chat-ui
publication branch   main
release class        offline candidate
```

The exact repaired implementation checkpoint is commit `6c66eff1ce200c4d07506310794ea9ac89a42895` / tree `5172fb7b0d72d3a733ec06bf7aa1d7f598b68e2f`. The checkpoint history and independent twin replay are in `docs/V06_OFFLINE_CHECKPOINT.md`.

## Publication boundary

- Merge and tag are authorized after the merged tree passes the complete offline gate.
- The repository currently has no configured Git remote. The tag is therefore a local publication marker until an operator separately supplies and authorizes a remote destination.
- This release does not claim that the unexecuted live gate passed. It does not activate a v0.6 provider route, perform provider generation, migrate shared runtime state, deploy a service, publish credentials, or grant acceptance/resident authority.
- Stable `v0.6.0` remains a later decision after the operator-controlled live runbook, rather than a silent rename of this verified alpha.
