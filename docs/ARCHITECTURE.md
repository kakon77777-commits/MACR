# MACR v0.1 architecture

```text
Codex or another primary host
        |
        v
TaskContract
        |
        v
ProviderRegistry -- policy/auth/privacy gate
        |
        +--> MiniMax OpenAI-compatible adapter
        +--> Grok pending adapter (disabled)
        +--> Claude subscription adapter (disabled)
        |
        v
ProviderResult(status=candidate_*)
        |
        v
Verifier / operator acceptance (future v0.2)
        |
        v
Append-only ledger on R:
```

## Native Codex boundary

Official Codex custom providers are configured at user level and currently use the Responses wire API. Project-local `.codex/config.toml` cannot override `model_provider` or `model_providers`.

MACR therefore does not pretend every vendor is a native Codex provider. It supports two distinct routes:

1. A provider that passes Codex Responses compatibility may be configured as a Codex backend in the future.
2. Any approved provider may be called through a MACR adapter and returned as a normalized candidate.

This repository implements route 2 for MiniMax first. It does not edit user-level Codex configuration.

## Commit boundary

Provider completion is not task completion:

```text
generation != verification != acceptance
```

The runtime records dispatch and candidate completion. v0.2 will add verifier decisions and accepted-result events. Until then, all successful provider output remains `candidate_success`.

## Failure behavior

- Missing credentials: fail closed before network activity.
- Missing CLI network opt-in or a zero cost budget: fail closed before network activity.
- Disabled provider: fail closed with the recorded policy reason.
- Privacy mismatch: fail closed before network activity.
- Missing declared capability: fail closed before network activity.
- Invalid or oversized response: candidate failure with no acceptance.
- Oversized request or any HTTP redirect: fail closed; bearer credentials are never forwarded by redirect handling.
- Remote HTTP error bodies: omitted from normalized errors to avoid reflecting provider-side sensitive content.
- Stale or duplicate external result: future orchestration must compare task/event identity before committing.

`max_cost_usd > 0` is a required authorization gate in v0.1, not proof of the final billed amount. Live activation remains blocked operationally until current pricing and response usage are checked.
