# MACR v0.7 provider-admission uncertainty isolation candidate

Date: 2026-09-12

Status: read-only shared-state evidence plus offline implementation candidate;
no policy transition, provider call, retry, charge resolution, or shared-state
write is authorized or claimed by this record.

## User-visible defect

MACR already allowed multiple projects and configured GLM capacity at
effective/review/hard `8/16/32` with per-project cap 8. Historical admission
policy revision 2 nevertheless converted any `reconciliation_required` request
into provider-wide `OPEN`. One uncertain request therefore blocked the other
seven capacity units. This was a policy-semantics defect, not a one-address or
single-worker configuration.

## Exact shared readback

The 2026-09-12 readback used only SQLite/CLI read paths and reported:

```text
provider                     glm_flash_worker
stored policy revision       2
stored policy digest         b6688485aec5ea1c4845d650ab1fc162813540f2f644db509ae374f50a0bd3c6
uncertainty scope            global
effective/review/hard        8 / 16 / 32
per-project cap              8
circuit                      open
last signal                  unknown_after_dispatch
completed                    69
reconciliation_required      1
waiting/granted/dispatched   0 / 0 / 0
```

The one preserved request is:

```text
request_id                   c69ef535-49c3-4220-95c4-5aa7d2933ef9
run_id                       989fd0ee-439f-46a2-b5b8-b88238ba4d6f
project binding digest       4737df6a81f3f3347a859cc821b9b5da5d7953d85ae1f6bfee930ec325e03e51
lane                         routine
request state                reconciliation_required
transport started            2026-09-11T08:35:38.219245+00:00
terminal recorded            2026-09-11T08:37:56.656482+00:00
terminal evidence digest     8f07accede131ca72b0f86cc06c6748536d8f05f8155676fbc1d14286815835e
```

The independent accounting row remains:

```text
billing state                unknown_after_dispatch
currency cost                NULL
cost kind                    NULL
candidate state              candidate_failure
failure                      ConnectionResetError / provider_execution
duration                     138417 ms
network_attempted            NULL
response_received            NULL
HTTP/provider/transport      NULL / NULL / NULL
```

No 429/5xx pressure transition follows the opening transition. The final six
control records are five closed `http_200` terminals followed by control
revision 72 `unknown_after_dispatch` for the exact request above.

This evidence does not determine whether the provider charged the request. It
does not resolve the billing row and must never be interpreted as zero cost.

## Candidate correction

- GLM policy revision 3 and Grok policy revision 2 bind
  `uncertain_dispatch_scope=capacity_reservation` into new policy digests.
- A durably terminalized no-response request remains
  `reconciliation_required` and keeps one global plus one project capacity
  unit, while a closed provider circuit stays closed.
- Capacity reaches BUSY normally after all effective units are occupied by
  active or unresolved requests.
- Missing terminal evidence and HTTP 429/5xx remain provider-wide stops.
- A later sibling 200/400 cannot close an already open circuit.
- Reconciliation releases only its named capacity unit and never controls the
  circuit or accounting state.
- T1 reconciliation blocks its own plan, not unrelated plans/projects.
- An unstarted expired grant is cancelled and releases capacity; an expired
  dispatched permit remains unresolved and capacity-consuming.

Historical GLM r2 and Grok r1 databases reopen against their exact stored
digests. They do not silently acquire the new semantics. A forward transition
requires the exact old/new policy digests, target, a reviewed isolation
evidence digest when unresolved rows are preserved, a digest of the exact
control head plus ordered unresolved request records, and one consumed
transition authority. Apply recomputes that database snapshot under the same
write transaction, so a late sibling unknown or control transition invalidates
the reviewed binding. The migration retains the old request policy digest,
terminal evidence, project count, billing state, and NULL cost.

## Operational boundary

The implementation exposes a network-free two-step command:

```powershell
.\scripts\macr.ps1 admission-policy-upgrade `
  --provider glm_flash_worker --target 8 `
  --reconciliation-isolation-evidence-digest <this-file-sha256>

.\scripts\macr.ps1 admission-policy-upgrade `
  --provider glm_flash_worker --target 8 --apply `
  --reconciliation-isolation-evidence-digest <this-file-sha256> `
  --expected-binding-digest <digest-from-preflight>
```

The first command is read-only. The second is a shared operational mutation
and remains unexecuted at this checkpoint. It does not call GLM or read a
provider credential.
