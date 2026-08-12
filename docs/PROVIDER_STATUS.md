# Provider status

Updated: 2026-08-12

| Provider | Required | Transport | Credential mode | API billing allowed | Runtime state |
|---|---:|---|---|---:|---|
| MiniMax | yes | configurable OpenAI-compatible HTTP | API key environment variable | yes | adapter implemented; live configuration absent |
| Grok | planned | Responses-compatible candidate | pending API application | yes, after approval | disabled |
| Claude | optional | subscription client, exact client pending | paid subscription login | no | disabled |

## MiniMax activation gate

Official compatibility check performed 2026-08-12:

- MiniMax documents an OpenAI-compatible base URL of `https://api.minimax.io/v1`.
- The documented text endpoint is `POST /v1/chat/completions` with Bearer authentication.
- MACR allowlists `api.minimax.io`, while the base URL and model remain external environment values.
- The operator must still choose between a pay-as-you-go key and a Token Plan key; MACR will not silently switch credential classes.

Sources:

- https://platform.minimax.io/docs/api-reference/text-openai-api
- https://platform.minimax.io/docs/api-reference/text-chat-openai
- https://platform.minimax.io/docs/guides/quickstart-preparation
- https://platform.minimax.io/docs/pricing/overview

All of the following are required before the first live request:

- the intended MiniMax account, credential class, and model ID selected;
- `MINIMAX_API_KEY`, `MINIMAX_BASE_URL`, and `MINIMAX_MODEL` set outside the repository;
- a low-cost, non-sensitive conformance prompt approved;
- response shape, usage fields, timeout, cancellation behavior, and error mapping recorded;
- the result remains a candidate until separately verified.

## Grok activation gate

Do not invent or borrow credentials. The provider remains disabled until the operator obtains API access and asks for activation.

## Claude boundary

Do not read or use `ANTHROPIC_API_KEY`. A future subscription-client adapter must be explicitly selected and tested. It must never fall back to Anthropic API billing.
