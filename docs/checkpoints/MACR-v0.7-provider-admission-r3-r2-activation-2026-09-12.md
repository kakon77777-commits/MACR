# MACR v0.7 GLM r3 and Grok r2 shared activation receipt

Date: 2026-09-12

Status: canonical shared provider-admission policies activated; no provider
request, credential read, generation, retry, fallback, billing resolution,
Hosted Agent DB adoption, release tag, or `v0.7.0a1` claim.

## Code subject and merge

The offline Hosted Agent Cell/provider-isolation candidate passed on:

```text
commit                       91e6309fda698922d5b20276802eb646f1830095
tree                         465e7bfb38b7ce9f78a949a9bff3c8bb9d7e9325
focused tests                164
required test IDs            38
inherited tests              969
Phase-C focused tests        98
network/provider generation  false / false
shared migration by gate     false
canonical v0.7.0a1 closed    false
```

One earlier complete-wrapper attempt on the same subject stopped at a Windows
`SpawnProcess-34` bootstrap message. A standalone Phase-C gate then completed,
followed by one complete Hosted Agent Cell wrapper. The initial RED is retained;
two consecutive complete wrapper passes are not claimed.

Canonical local `main` fast-forwarded from
`bcb223672bbf60784822ac2237e5bc496f82d803` to the exact subject above. The
pre-existing untracked `REQUEST_FOR_CODEX_T1_LIVE_ROUTE.md` and
`scripts/invoke-grok.ps1` were preserved.

## Pre-activation safety boundary

The exact GLM invoker census was zero. A SQLite-native consistent backup was
created before either transition:

```text
path    D:\AI_RESIDENCE\AI_Runtime\macr-state\backups\provider-admission-pre-r3-r2-20260912-220517.sqlite3
bytes   6590464
sha256  b902eb73a543bc860ceb48489ec9462fcceb55a507114180705f5d3df597a35a
integrity_check  ok
```

GLM preflight bound:

```text
from/to policy revision      2 -> 3
from policy digest           b6688485aec5ea1c4845d650ab1fc162813540f2f644db509ae374f50a0bd3c6
to policy digest             731de4f9c6592e6c35b97d5b5d69b6fe5e19a3782c22c014e0e2ee0407d5a74c
target                       8
binding digest               70fcf82b6c0526e4d1956b12a170aa583226a5b00c2dd6ee11c1698cc0a1741e
reconciliation snapshot      a4ba9faafbadc1f01ef435423e0df2c69d2c132e801602a658ff8e058d430e3d
review evidence digest       0559f9b7a8f1366a27ee246b70cf0b95548a18383dfc1ccb7906b4fb9d0fa012
```

Grok preflight bound:

```text
from/to policy revision      1 -> 2
from policy digest           bc9b2cc9e3d4e57de1613daf66d323f05942b6281d7a5540e4fbe910b37bf4fe
to policy digest             310dcdeb78ce27bccabec30d1940c87bbe409360c38b62298445aed57154d390
target                       8
binding digest               6866a0887865b7991c08d9bf227a2fac99d05fc4f9f0c77aa3261427c3f16031
reconciliation snapshot      none
```

## Activation readback

GLM transition:

```text
authority digest             56b6012b824ffeb20328e41ef203982b92bf1212085197209e67364e946af43c
transition id                6435fd88-6013-4e1f-b3bd-874818c09738
control revision             73
control/body digest          8e08424da9c61552fd6403b327a444427f9d6f8fa4d57c4e9096fed4fc0a2122
deployment digest            51bf02781795fe429a180f3f6cba7cf78be2d24fa8081733f2a0418b43f0a036
effective/review/hard        8 / 16 / 32
per-project cap              8
circuit                      closed
last signal                  policy_superseded_with_reconciliation
```

The historical request `c69ef535-49c3-4220-95c4-5aa7d2933ef9` / run
`989fd0ee-439f-46a2-b5b8-b88238ba4d6f` remains
`reconciliation_required` under the old r2 policy digest, retains terminal
evidence `8f07accede131ca72b0f86cc06c6748536d8f05f8155676fbc1d14286815835e`,
and continues consuming one project/global capacity unit. Accounting still
reports `unknown_after_dispatch=1`, `currency_cost_usd=NULL`, and
`ConnectionResetError/provider_execution`; no zero-cost inference occurred.

Grok transition:

```text
authority digest             4adcca84dc96b2b8d50480f7ceb464390beb50ca013ca7f2f6accbc8d55ddd50
transition id                ae4920eb-7df3-4b76-b1b1-b2b2fc56f67c
control revision             2
control/body digest          cd1ae9d9b7de5273b15cab2e1b97c94b9b8e29a899e06db61acb7303b898cbeb
deployment digest            4d8d65ade1d3b8fe021610e42695fa59d619b1c72adb2e27ea48f48185727743
effective/review/hard        8 / 16 / 32
per-project cap              8
circuit                      closed
requests                     0
```

The final invoker census was again zero. This activation changes provider
admission semantics only. It does not prove live safe concurrency at target 8
and does not activate Hosted Agent Cell persistence or a live Agent route.
Post-activation `dispatch.sqlite3` also returned `PRAGMA integrity_check=ok`;
the historical GLM r1/r2 and Grok r1 policy rows remain present beside the new
GLM r3/Grok r2 rows.
