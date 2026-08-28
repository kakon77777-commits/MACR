# MACR v0.5.0a2 Shared Core — Checkpoint A repair candidate

Status: local review candidate; not accepted, merged, released, deployed, or published externally.

Date: 2026-08-28

## Preserved a1 boundary

The repair starts from the exact unaccepted v0.5.0a1 candidate:

```text
a1_candidate_commit = bf9ef62168cb8742d5a3f5949974a9ca4f66598e
a1_candidate_tree   = ec97dcf665c328852d3597ff5373b4369705b173
```

Historical evidence remains unchanged:

| Artifact | Bytes | SHA-256 |
|---|---:|---|
| `docs/CHECKPOINT_A_SHARED_CORE_2026-08-27.md` | 8,834 | `E6A9D6C32A4782BA3BD1459F9474BC03B1FFB36B3981FBB98D0FE5292379A3C7` |
| `2026-08-27-pragma-macr-v05-checkpoint-a-replay.md` | 7,726 | `FECB55E09CF686A1C0F12C0C6DB6DB98198924A1BD4EB2993D6E239D13A85150` |
| `2026-08-27-metron-macr-v05-checkpoint-a-replay.md` | 10,063 | `4DC7E738789E925B42E23AD202107A87EE673144B63EF8FF3F4394ACD1666537` |

The implementation-only repair boundary before version and documentation edits is:

```text
implementation_commit = b6cbab09bc792d83f706e82caf34b19313ffc1b7
implementation_tree   = d6b599505b9d47da3a291528a42c159f7a93bf43
```

The final repair commit cannot self-record its own ID; reviewers must recompute the exact candidate commit/tree supplied in the handoff.

## Independent diagnosis

The a1 candidate was not accepted. Reproduction separated four findings:

1. **SQLite bootstrap race — confirmed code defect.** Twelve unsynchronized reruns passed, but a synchronized 16-process fresh-database probe failed on iteration two with seven processes raising `sqlite3.OperationalError: database is locked` at `PRAGMA journal_mode=WAL`.
2. **Event privacy boundary — confirmed code/contract defect.** `path`, `source_path`, and `remote_body` fields were accepted and readable; `prompt` alone was rejected.
3. **Plain-source wrapper — confirmed contract defect.** `Here is the source:\nexport {};` was incorrectly returned as `plain_source_valid` despite the provider instruction forbidding prose.
4. **Bare replay command — confirmed documentation defect.** `python -m unittest tests.test_multiprocess_runtime -v` failed from the source checkout without `PYTHONPATH=src` and passed after that environment was supplied.

`JSON_OBJECT` accepting whitespace, a final newline, and member reordering is not classified as a defect. It is a semantic unique-key object contract. Byte-exact JSON requires `EXACT_TEXT`.

## Repair contract

### SQLite bootstrap

- WAL negotiation occurs during runtime-database bootstrap, not every ordinary connection.
- Bootstrap retries only transient SQLite `BUSY/LOCKED` results, with a 30-second monotonic deadline and 10-millisecond retry interval.
- Failed bootstrap connections close before retry.
- Ordinary connections verify persisted WAL mode and fail closed if it changed.
- Provider transport remains single-attempt; database bootstrap retry grants no provider retry authority.
- A deterministic injection test forces the first two WAL attempts to raise `database is locked` and requires the third to succeed.
- A real 32-process barrier test constructs one fresh shared database and requires every process to observe schema version 4 and WAL mode.

### Operational event privacy

- Dispatch and terminal events enforce required keys and reviewed field value types before transaction start, not only top-level names.
- Candidate-capture metadata must be null or a complete typed object with its exact reviewed key set.
- Every event API recursively rejects prompt/answer/credential plus path/body/content keys, including snake_case, kebab-case, ordinary camelCase, and acronym-bearing camelCase forms normalized to `_path`, `_paths`, `_body`, and `_content` suffixes.
- Windows drive-absolute, drive-relative, backslash-UNC, and forward-UNC path-like string values are rejected even under an alias key.
- HTTPS URLs and `hf.co/...` model identifiers are positive controls and remain permitted.

### Return contracts

- `PLAIN_SOURCE` rejects Markdown fences, evidence/warning sections, common leading wrappers, and headings dynamically derived from the task's declared language.
- Generic `Source:`/`Code:` wrappers require the colon to end the line, so valid source such as Python `code: str = 'ok'` remains accepted.
- Ordinary source comments remain valid.
- This is a conservative format guard, not a language parser or compilation proof.
- `JSON_OBJECT` remains semantic-object validation; `EXACT_TEXT` remains the byte-exact contract.

### Replay environment

The dedicated command is self-contained when run as:

```powershell
$env:PYTHONPATH = Join-Path (Get-Location) 'src'
python -m unittest tests.test_multiprocess_runtime -v
```

The complete gate remains:

```powershell
.\scripts\verify.ps1
```

## Primary-agent verification before twin replay

Observed final post-twin pre-commit full gate:

```text
Ran 250 tests in 17.076s
OK (skipped=2)
doctor version = 0.5.0a2
doctor network_activity = false
process census count = 0
```

Observed dedicated gate:

```text
Ran 6 tests in 13.825s
OK
```

The synchronized 32-process bootstrap subject also passed eight consecutive additional executions after repair. The two full-suite skips remain the Windows symlink/reparse capability controls; no symlink safety claim is added.

## Known boundaries after repair

- No live provider, local model, real operator-ledger migration, Direct Chat, host adapter, fan-out scheduler, Context Capsule, verifier decision, or acceptance transition is exercised.
- Runtime and accounting remain separate databases without one cross-database transaction.
- Leases still have no in-flight renewal loop; workspace-write collision remains repository-wide.
- Candidate bytes remain unencrypted under the D-drive access-control boundary.
- `PLAIN_SOURCE` cannot prove arbitrary natural-language prose absent or source compilable; independent compilation/verification remains required.
- Generic standalone diagnostics remain caller-governed beyond the explicit recursive key/path guards. Operational runtime events are the strict allowlisted boundary.
- SQLite bootstrap retry has a bounded deadline; persistent lock or storage failure remains a real failure and is not hidden.

## Single twin review and post-twin closure

The one authorized twin reviewed exact candidate `d0aff2858b263492d2d75e9a22b2a20e41b08ecf` / tree `700f96674c6a7761ea825b91947a26fc39bd1d09` read-only. Its full and dedicated gates passed, including eight observed synchronized-bootstrap executions, but it returned **Not ready** after finding:

1. acronym-bearing camel aliases and forward-UNC/drive-relative path bypasses;
2. operational schemas that constrained names but not value types or candidate-capture shape;
3. hardcoded language headings that missed Python/Rust/`TypeScript source:`;
4. a generic `code:` pattern that rejected valid Python annotation syntax.

The implementation boundary recorded above adds independent RED/GREEN tests for each exact finding. The twin seat is consumed; no second subagent review is authorized. Final post-twin evidence is produced by the primary agent, remains verification rather than acceptance, and grants no merge/release authority.
