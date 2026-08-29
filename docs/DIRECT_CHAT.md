# MACR Direct Chat UI 0.1 Operator Guide

Status: retained Direct UI `0.1` under `MACR 0.6.0a1`, 2026-08-30

This is the executable Direct plane for provider-native Grok 4.6 and local Qwythos conversations. It is not the future MACR v0.6 dynamic-coordination runtime. The v0.6 design and implementation plan remain separately versioned and unchanged.

## Install and open

From the isolated a4 candidate checkout:

```powershell
Set-Location 'D:\Ai\work together\MACR\.worktrees\macr-v0.6-dynamic-coordination'
.\scripts\install-direct-chat-shortcut.ps1
```

The resulting Desktop entry is **MACR Direct Chat (Alpha)**. It points to `scripts\start-direct-chat.ps1` on D: through hidden Windows PowerShell. The link and its arguments contain no xAI key and no browser bootstrap token.

On launch, the PowerShell entry point:

1. resolves the a4 source tree and D-drive runtime root;
2. invokes the repository's `scripts\read-grok-key.ps1` bounded loader against `D:\KEY\GROK.txt` without printing the returned token or diagnostics;
3. injects the token into the hidden child process only;
4. starts or reopens one loopback Direct server;
5. clears the parent PowerShell environment value;
6. opens the default browser with a one-time fragment bootstrap.

The loader accepts only one bounded non-whitespace `xai-...` API secret. A UUID-shaped console identifier is not an API secret and is rejected locally. The credential file must be an ordinary D-drive file, not a reparse point. Missing or invalid Grok credentials disable only the Grok card; the service and local Qwythos remain available.

The server shuts down after 30 idle minutes by default. Active requests and unsettled accounting keep it alive. Launching the shortcut again opens the existing instance when it is reachable.

## Interaction contract

- Select either **Grok 4.6** or **Qwythos** before creating a conversation.
- Provider and model cannot change inside a conversation.
- The system-prompt field is visible and blank by default. Blank means no system message. Nonblank text is stored visibly and sent exactly once at the start of every full-history request.
- Every request carries all stored user/assistant turns. Direct UI 0.1 does not silently summarize, compact, truncate, route, retry, or switch models.
- While generating, the UI shows model and elapsed wall time only. It has no fabricated percentage and does not stream partial tokens.
- A completed answer is privately captured and accounted before it is atomically added to history. Model text is rendered as exact safe pre-wrapped text, not executable HTML.
- Search, archive, restore, active settings, and provider-account summaries are local UI functions.
- Sampling/budget settings remain global, while context warning, hard context, default output, and maximum output are selected per exact provider/model from `model-token-policies.sqlite3`. A new conversation pins that policy digest; an override never silently changes an existing conversation or Qwythos when Grok is edited.

## Provider boundaries

### Grok 4.6

- Exact provider/model: `grok` / `grok-4.6`, reasoning effort `high`.
- Request uses xAI Responses input roles, `store=false`, no tools, no previous response ID, one transport attempt, and a bounded maximum output.
- Conversation dataset role is `archive_only`; local `training_eligible=false`.
- The settings preference `provider_improvement_preference=allowed` is recorded, but it does not prove provider retention, deletion, or training behavior.
- Provider-reported cost ticks are normalized and written to the shared AI-expense subledger. Missing cost remains explicitly unknown.
- Failed turns show their sanitized failure type in the UI instead of appearing as an empty response.

### Qwythos

- Exact provider/model: `ollama_qwythos` / `hf.co/empero-ai/Qwythos-9B-v2-GGUF:Q4_K_M`.
- Route is exactly `http://127.0.0.1:11434`; no Ollama Cloud, key, tool, vision, pull, or model modification is permitted.
- The installed model digest is pinned at conversation creation.
- Requests use `stream=false`, `think=false`, full message history, and local zero-API-cost accounting.
- Conversation dataset role is `eval_only`; local `training_eligible=false`. The canonical model weights remain immutable.

## Persistent state

```text
D:\AI_RESIDENCE\AI_Runtime\macr-state\
  direct\conversations.sqlite3
  direct\instance.json
  direct\instance.lock
  settings\settings.sqlite3
  settings\model-token-policies.sqlite3
  runtime\dispatch.sqlite3
  accounting\accounting.sqlite3
  candidates\<provider>\<run-id>\answer.bin
```

Conversation and settings databases are plaintext in UI 0.1 and record `encryption=none`. The browser never receives provider credentials, candidate file paths, authorization bodies, or remote error bodies. Operational/accounting databases contain content-free identity, authority, model, usage, cost, duration, state, byte count, and hash metadata; exact prompt/answer text stays in the private Direct database or Candidate Vault.

## Archive and permanent deletion

Archive is reversible. Archived conversations remain plaintext on D: and can be searched, opened, and restored when archived history is enabled.

Permanent deletion is deliberately harder:

1. select the conversation and press **永久刪除**;
2. type exact uppercase `DELETE` in the browser confirmation;
3. deletion refuses while that conversation has an active run;
4. unmaterialized Candidate answer files for its runs are overwritten best-effort and removed;
5. system prompt, user/assistant messages, Direct runs, and conversation row are deleted with SQLite `secure_delete=ON`;
6. the Direct WAL must checkpoint and truncate successfully;
7. the UI removes the thread and reports message/run/Candidate counts.

MACR retains only content-free provider accounting, operational hashes/Candidate metadata, and a `direct.conversation_deleted` tombstone. Permanent deletion does not ask Grok or another provider to delete already transmitted data and cannot guarantee physical NAND erasure under SSD wear leveling. Filesystem snapshots, external backups, materialized copies, and provider retention require their own deletion controls. No current conversation is deleted automatically.

## Manual alpha acceptance

The implementation gate is offline/local and does not spend Grok credit. The operator completes the remaining live acceptance from the UI:

1. Open the v0.6 checkout's launcher and confirm the header says `MACR 0.6.0a1 · Direct UI 0.1 alpha`.
2. Confirm Grok reports a configured state and Qwythos reports the installed local model/digest.
3. Create a Qwythos conversation with a blank system prompt. Send two turns where the second depends on the first. Refresh/reopen and confirm all four messages persist in order.
4. Create a Grok conversation with a short, visible system prompt or a blank prompt. Send two bounded turns where the second depends on the first. Confirm the response appears only when complete.
5. Open Settings and Accounting. Confirm Qwythos is `zero_local`; confirm Grok cost is provider-reported or explicitly unknown, never silently zero.
6. Search for each conversation, archive it, enable archived history, and restore it.
7. Inspect no provider response as delegated verification or acceptance. These are Direct conversation records only.

## Alpha limits

- No Direct GLM, Google, MiniMax, Claude, or Grok 4.3 selection.
- No cross-provider context copy and no Direct-to-Codex/Claude Context Capsule.
- No tools, web-search controls, files, images, or voice surface.
- No automatic retry, summarization, compaction, routing, verification, materialization, or acceptance.
- No transport-level cancel control or explicit late-result recovery in UI 0.1. These are required before `0.5.0b1`.
- No merge, release, deployment, publication, or v0.6 implementation follows merely from installing this local alpha shortcut.
