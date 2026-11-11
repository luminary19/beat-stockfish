# Implementation and startup report

**Running independently. No completed outcomes yet.** The continuing supervisor is
PID **1300728**, executor **1301013**, and the first four actor PIDs are **1301036,
1301037, 1301038, 1301039**. OpenCode background shell ID:
`sh_1b1eebdf0001dzaK4PovhlzhhC`. The existing OpenCode service owns the background job.

## Verified startup evidence

- 40 offline tests passed: `offline-verification.txt`. These include three-batch
  continuation, four-slot concurrency, exactly three logical slots per candidate,
  no replay of completed/ambiguous slots, crash recovery, inherited Linux locks,
  typed quota versus generic-429 classification, transcript exclusion, exact prompt
  and asset measurement, absent/empty distinction, and installed adapter interfaces.
- Native tick 1 actually ran and exited 0; proposal accepted and committed:
  `../ticks/t0001/{proposal.json,finished.json,accepted.json,events.jsonl}`.
- Infrastructure commit: `d5c84af`; native decision: `1a3be78`; first frozen protocol:
  **`e6c3b584a773ed8a4f4e93798b3c1bfdcbfac1fe`**, before actor processes started.
- `../../logs/minimal-prompt-hillclimb/startup.json` records the four actor PIDs and
  protocol commit at **2026-11-06 17:37:17 UTC** (November 7 in the host's local date).
- `../../logs/minimal-prompt-hillclimb/first-actor-request.json` records entry into
  the real OpenAI model-generation call at **17:37:38 UTC**, actor PID 1301039.
- Process inspection confirmed supervisor → executor → four live actor processes.
  Docker inspection confirmed four fresh `beat-stockfish:local` sandbox containers.
  Every actor console recorded `campaign_actor_runner_entered` with unchanged
  100 turns, 10,800 seconds, high reasoning; no extra game runs were used for testing.

## Initial pair: three logical replicates each

| ID | Linked phrase | Added visible prompt words | Deleted / word-edit distance | File words / bytes | Link markup bytes | Link-target lexical words | Total non-original lexical content |
|---|---|---:|---|---|---:|---:|---:|
| c800f68970968 | `[your own ability](definition.md)` | 1 | 0 / 1 | 0 / 0 | 17 | 2 | 3 |
| cbe90458a394a | `[your ability](definition.md)` | 0 | 0 / 0 | 0 / 0 | 17 | 2 | 2 |

Both assets were verified **genuinely zero bytes**, not absent. Targets tokenize as
`definition` and `md` under the preregistered lexical rule. Zero visible additions
is therefore a structural intervention, not an unchanged prompt or a free link.
Exact prompts, full diffs, hashes, hypotheses and configuration are in
`../candidates/<id>/`. Replicates 1–2 for each are active; replicate 3 for each is
preregistered and will fill released slots without exceeding four actors.

## Continuing control and safeguards

After each bounded batch the supervisor ingests all outcomes, commits results,
and foreground-invokes the next native director tick. This is **not a one-shot
sweep** and does not require further approval. The first real native invocation
already exercised this path. Offline tests additionally exercised three consecutive
batches. Later adaptive batches have not yet occurred at startup.

Ticks have a 24-step/20-minute bound, only current-proposal write permission, local
read access and one read-only validator command; actor launches, delegation and
network tools are denied. The campaign continues across ticks until confirmed
existing-quota exhaustion, user stop, or an explicitly reported infrastructure blocker.
No extra replicate is authorized for a promising candidate. A measured clean 3/3
remains exploratory and only becomes a provisional incumbent after full tool-trace
audit; alternate computation stays explicit. Missing/error/partial games never count
as clean. Remaining quota is **unknown**.

Campaign-only retries: Inspect request retries 2, SDK retries 0, task/sample replays
0. Quota/auth detection uses actual transport exceptions or saved error evidence,
not transcript words. The unchanged normal actor/grading/debrief budgets are frozen.
No shared runner, environment packages, proxy configuration, image, or main-checkout
user work was modified. Full retry/proxy audit: `../README.md`.

## Locations and stopping

- State: `autoresearch/research-state.json`
- Append-only ledger: `autoresearch/research-log.jsonl`
- Leaderboard: `autoresearch/leaderboard.json`, `autoresearch/leaderboard.md`
- Findings: `autoresearch/findings.md`
- Latest batch report: `autoresearch/to_human/LATEST.md`
- Raw logs: `logs/minimal-prompt-hillclimb/`

From the dedicated worktree, graceful stop (stop scheduling, let active games finish):

```sh
touch autoresearch/STOP
```

Immediate campaign-only stop, including an active native tick:

```sh
kill -TERM "$(cat autoresearch/supervisor.pid)"
```

Partial evidence is preserved. Never remove STOP or restart automatically after quota
exhaustion. Ambiguous started episodes pause for reconciliation, never silent replay.
