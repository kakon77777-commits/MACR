# Codex → MACR

Codex can invoke the same MACR CLI examples documented for Claude Code. The
ordinary shell route remains honestly attributed as `cli` / `process_id`; local
`CODEX_THREAD_ID` and `CODEX_SESSION_ID` are distinct and are not treated as
aliases or dispatch authority.

The in-process `MacrHostAdapter` is reserved for an embedding that supplies both
a host-owned verifier and pre-issued operator authority/connectivity grant. It
cannot issue authority, activate a provider capability tier, read Direct Chat
history or obtain a provider key during preflight. Live Codex host binding is
`NotMeasured` in this checkpoint.

See `integrations/claude-code/README.md` for the current CLI examples; the
provider, budget, approval, candidate and accounting behavior is identical.
