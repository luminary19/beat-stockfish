# Continuing minimal-prompt campaign

## Current user steering: timed exploration then 5 × 10 confirmation

The November 8 request supersedes the indefinite campaign and the earlier
three-replicate-only restriction for the explicitly authorized confirmation phase.
`phased.py supervise` takes over at the current batch boundary, under the same
inherited campaign lock. Its handoff STOP marker is temporary and ownership-checked;
it will not clear an unrelated user stop or resume an exhausted quota.

- Priority pilot: **your own reasoning** directly in the original sentence, no
  definition asset or link, three episodes. The bare **own reasoning** replacement
  is excluded.
- Exploration deadline: **2026-11-08 11:31:58 UTC**. This is five hours from the
  request; setup and handoff time count. Cutoff interrupts unfinished exploration,
  preserving partial evidence and never replaying it. Cancellation has a short
  process-cleanup grace period; no confirmation starts until actors have exited.
- Then select five eligible exact prompt/asset packages and freeze the selection
  before any confirmation outcome exists. Ten NEW episodes each, maximum four
  concurrent actors, original per-episode budget/model/tools/grading/debrief.
- Selection reserves the fully measured user-priority inline pilot as an informative
  transfer test; then chooses best clean-rate/minimal-text linked reasoning,
  knowledge, and explicit-definition candidates, filling remaining places by
  performance and minimality. Partial/invalid pilots and duplicate fingerprints
  are ineligible. Exact policy is preregistered in `phase-request.json`.
- Confirmation metrics remain separate from three-game pilots. Selection doesn't
  imply a full trace audit; pending audits and alternate-computation flags remain
  explicit. No claim of wholly unaided play follows from supplied-engine non-use.

Authoritative controller state: `phase-state.json`; live report:
`to_human/PHASED.md` (also `to_human/LATEST.md`). The existing `research-state.json`
retains pilot outcomes and points to the new phase state. Selection/protocol and
fresh confirmation results: `confirmation/{protocol.json,results.json,results.md}`.
Raw confirmation evidence: `../logs/minimal-prompt-confirmation/<id>/run-01..10/`.
All phase transitions stop on confirmed quota exhaustion or a real blocker.

Graceful user stop remains `touch autoresearch/STOP`. Immediate stop of the phased
controller: `kill -TERM "$(cat autoresearch/phased.pid)"`. During handoff, replacing
the temporary STOP contents with `user_stop` cancels continuation; the active legacy
games finish normally. Do not start a second supervisor. Ambiguous starts and
interrupted native ticks require reconciliation, never automatic replays.

Verification: **53 offline tests passed** on 2026-11-08 at 06:41 UTC with
`.venv/bin/python -m unittest discover -s autoresearch -p 'test_*.py' -v`.
The new tests cover the complete handoff → prioritized pilot → deadline → 50-game
transition, exactly ten unique slots per selected candidate, four-slot concurrency,
no replay, quota interruption, exclusion of invalid pilots, and preservation of
user stop markers. No actor API requests were used for verification.

## Original supervisor (historical implementation)

Start (after initialization): `.venv/bin/python autoresearch/campaign.py supervise`.
Run that as an OpenCode background shell. The supervisor foreground-waits on a bounded
batch executor; after ingestion and a result commit it invokes a fresh native
`opencode --standalone run --agent autoresearch-director-tick --model openai/gpt-6-astra#high`
tick. Each tick selects 1–2 candidates, not a finite campaign sweep. Native tick 1 also
selects and preregisters the initial pair before any actor starts. No additional approval needed.

Graceful stop: `touch autoresearch/STOP` (no new episodes; active games may finish).
Immediate stop: `kill -TERM "$(cat autoresearch/supervisor.pid)"` (campaign-owned children
only; preserves partial logs). Never use killall or touch the main checkout. Do not delete
STOP/restart after exhausted quota. Restart of an ambiguous started episode or interrupted
tick pauses for reconciliation instead of silently replaying it. Completed slots are read,
not re-run. A Linux advisory lock is inherited by executor and actor children, preventing
overlapping campaigns even after supervisor loss. No cron/unowned detached queue.

Native ticks have a distinct narrow role under the restored director: 24 model steps,
20 minutes, no delegation/web/network shell. OpenCode permissions allow only local
evidence reads, the current proposal's exact path, and the fixed read-only validator
command. The tick inherits the campaign lock and its PID/PGID is saved; immediate stop
also terminates the native tick group. Persisted tick errors/return codes are rechecked
even when a proposal already exists. Freeze transactions are journaled and idempotent:
a restart publishes the existing committed batch instead of generating/replaying it.
Execution validates the schedule/config against the committed batch protocol and
requires exactly the three slots per candidate, not just mutable state fields.

State: `research-state.json`; append-only log: `research-log.jsonl`; costs/outcomes:
`leaderboard.{json,md}`; narrative: `findings.md`; latest report: `to_human/LATEST.md`.
Immutable protocols: `candidates/<id>/` and `batches/<id>/protocol.json`. Native tick
decisions/events: `ticks/tNNNN/`. Raw logs: `../logs/minimal-prompt-hillclimb/` ONLY.
The supervisor checks hashes/image identity before each batch. Git commits remain local
on `autoresearch/minimal-prompt-20261107`; no push/merge/reset. All three slots are frozen
per candidate; interrupted slots remain missing, not replaced with new replicates.

## Retry audit / deliberate error-path changes

Installed Inspect 0.3.286 defaults model max_retries to unlimited; OpenAI 3.42.0 defaults
SDK retries to two; the copied runner uses eval_set retry_attempts=1 (one task retry).
Campaign-local `actor.py` imports that unmodified runner and overrides only error paths:
Inspect max_retries=2 (up to three request attempts), SDK max_retries=0, task/sample
retry_attempts=0 and retry_on_error=0. Thus no fresh game is silently replayed on an API
error. Bounded request retries handle transient 429/5xx; persistent errors pause the
campaign as BLOCKER, never quota. Normal actor budgets/generation/tools/debrief/grading
are unchanged. Shared `.venv` packages and original checkout are never edited.

Live OpenAI exceptions are captured before Inspect flattens them: class, message,
code/type/body, status/request ID, traceback, stage. No headers/credentials are recorded.
Confirmed quota/auth errors are nonretryable. Debrief errors are also captured, despite
the runner normally saving them without raising. The executor watches these typed records
and stops scheduling on exhaustion; other active campaign actor groups are terminated
to avoid further requests. Saved EvalLog errors are secondary evidence. Ordinary model
text/tool output is NEVER a source of quota/error classification.

Local proxy audit: CLIProxyAPI 8.0.48, commit dbb70621; localhost:8317/v1. Installed
config has server/management/access/oauth sections and no retry/routing overrides.
One existing upstream OAuth credential file; no per-credential retry/cooling overrides.
Source `internal/config/config_load.go` at that exact commit initializes a zero-value
Config and does not set RequestRetry/MaxRetryInterval (both zero); config.go documents
those as extra rounds / cooldown wait cap. Thus no configured extra proxy retry rounds
or waiting for quota reset; no account pool to rotate. Proxy/credential files were read
for nonsecret settings only and NOT modified. This is a source/config audit, not a
remaining-quota measurement. Model availability is not quota evidence.
Source URLs fetched for implementation audit (not research claims):
https://raw.githubusercontent.com/router-for-me/CLIProxyAPI/dbb70621/internal/config/config_load.go
https://raw.githubusercontent.com/router-for-me/CLIProxyAPI/dbb70621/internal/config/config.go

## Measurement / scope

Exactly three logical replicates per distinct prompt+asset fingerprint. Four actor
processes globally at most under the inherited lock. Seeded allocation is not a model
seed. Failures/missing grades/partial games never count as clean. Clean 3/3 cohorts
await native full-tool-trace inspection before provisional promotion. All candidates,
including negatives and errors, remain in state/reports; no general robustness claim.
Rendered prompt words, edits, file words including headings, file bytes, link-target
lexical words and markup bytes are separately explicit. Total lexical cost includes
link-target tokens; a zero-visible-word linked edit is still labeled structural change.
No held-out confirmation, additional replicates, judge calls, or reliable numerical quota
counter are authorized. Historical own-only is fingerprint-blocked.

Tests: `.venv/bin/python -m unittest discover -s autoresearch -p 'test_*.py' -v`.
All scheduler/error tests use synthetic fixtures, not extra actor games.
