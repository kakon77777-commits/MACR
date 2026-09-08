# MACR v0.7.0a0 provider transport telemetry checkpoint

Date: 2026-09-08

Status: offline P0 implementation candidate. This is not a provider-side root
cause determination, retry authorization, billing reconciliation, release, or
deployment record.

## Exact implementation subject

```text
implementation_commit = ddcdb67048039bbaee6a23c2011e0b17443db109
implementation_tree   = d57ac3dd548b5875c88c036b6b29e3b3c714f17
branch                = fix/provider-http-telemetry
```

## Incident correction

The pre-repair lifetime accounting snapshot contained 29 all-provider
`unknown_after_dispatch` rows:

| Provider / failure shape | Rows | Dispatch-to-terminal observation |
|---|---:|---:|
| GLM historical untyped | 9 | 290–300 seconds |
| GLM `ProviderUnavailableError` | 13 | 280–291 seconds |
| GLM current `ProviderProtocolError` | 4 | 0.419–0.582 seconds |
| Grok historical unknown | 3 | separate provider |

On 2026-09-08 GLM recorded 17 estimated successes and four rapid unknown
failures. The relevant bounded batch window recorded 11 estimated successes
and four rapid unknown failures. The three repeated task identities retained
the same member, token-policy, and tier digests; two later succeeded and one
failed twice. Those successes do not settle the earlier runs. The four failures
had no overlapping invocation visible in MACR accounting.

The exact upstream HTTP/business code is irrecoverable from pre-repair data.
Rate limiting or provider capacity is a hypothesis, not a finding.

## Implemented boundary

- Shared HTTP transport extracts only a valid HTTP status and bounded
  top-level provider `error.code`; message/body bytes are discarded.
- Connection details are omitted rather than reflected into public errors.
- Request validation, connection, HTTP response, response read, and response
  decode are distinct bounded transport stages.
- Runtime exception paths retain measured duration and three-state
  `network_attempted` / `response_received` evidence.
- GLM successful responses record status 200 and `response_received` evidence.
- Accounting schema 4 and accounting-outbox schema 3 add five nullable
  transport fields. Terminal event contract 3 carries the same fields.
- `accounting-status --provider <id> --since <aware-ISO-time>` filters
  invocation totals and pending invocation outboxes and emits safe failure
  groups. Plan/bill-observation outbox counts remain global.
- `unsettled_count=0` remains process-terminal state, not invoice settlement.
  Unknown costs remain unknown and contribute no value to `known_cost_usd`.

No automatic retry, provider fallback, pacing, circuit breaker, task-policy,
worker-count, or billing-state relaxation was added.

## Verification evidence

RED/GREEN controls cover:

- HTTP 429 plus business code 1303 without remote-message retention;
- connection failure without DNS/TLS-reason reflection;
- malformed HTTP 200 response-boundary evidence;
- pre-open oversized request marked `network_attempted=false`;
- runtime/event/accounting preservation of typed safe telemetry and elapsed
  time;
- provider/date filter isolation and safe failure grouping;
- schema-3 read-only compatibility and additive 3→4 migration;
- HTTP error-body handle closure with `ResourceWarning` promoted to error.

The complete repository replay ran 822 tests with zero failures and two
existing Windows platform capability skips.

A copy of the live accounting database was migrated offline:

```text
source_schema_before          = 3
copy_schema_after             = 4
row_count_before              = 137
row_count_after               = 137
historical_field_digest_equal = true
new_nullable_columns          = 5
historical_transport_nonnull  = 0
source_database_unchanged     = true
replay_copy_removed           = true
network_activity              = false
provider_generation           = false
```

The live accounting database was not migrated during this checkpoint. Its
existing four rapid failures remain null forever. The first later invocation
under accepted code will migrate additively and can produce new telemetry; it
must not be initiated merely to test this checkpoint.

The governing Twin did not return within two bounded waits and was interrupted,
so no independent `CONCUR` is claimed. Primary behavioral, structural, and
discriminative evidence is recorded above; independent replay remains a later
acceptance input.
