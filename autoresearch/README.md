# Continuing minimal-prompt campaign

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
