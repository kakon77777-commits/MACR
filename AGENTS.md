# MACR workspace instructions

These rules apply to this repository and all descendants.

- Treat `D:\Ai\work together\MACR` as the canonical source and documentation root.
- Treat `R:\AI_Runtime\macr-state` as the default runtime-state root.
- Do not create persistent project, provider, cache, log, session, virtual-environment, or test-state files on drive C.
- Do not move or delete the existing Codex state on drive C without a separate, explicit migration request and a verified rollback copy.
- Never commit provider credentials. Read them only from named environment variables.
- Anthropic API use is forbidden by current operator policy. A future Claude integration must use an explicitly approved subscription-client route and must not silently fall back to API billing.
- Grok remains disabled until the operator has obtained and configured API access.
- MiniMax is the first required API provider. Network calls must remain opt-in; the default test suite is offline.
- Keep worker output as a candidate until verification accepts it. Generation, verification, and acceptance are separate states.
- Preserve append-only evidence for dispatch, candidate results, failures, and acceptance decisions.
- Keep provider-specific wire formats behind adapters. Do not leak them into `TaskContract`.
- Use environment-root indirection so SSD migration requires configuration changes, not source rewrites.
