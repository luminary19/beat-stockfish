# Campaign leaderboard

Status: running

3/3 is exploratory/provisional, not robust. Missing/partial/error ≠ clean. No wholly-unaided claim. Costs include file titles and link targets.

| Candidate | Clean / 3 | Engine use | Valid complete | Added / deleted / edit | File words / bytes | Markup bytes | Total new lexical | Provisional |
|---|---:|---:|---:|---|---|---:|---:|---|
| c398e61a30e0a | 3/3 | 0 | 3 | 0 / 0 / 0 | 23 / 161 (nonempty) | 17 | 25 | False |
| cb5d7952a9c16 | 0/3 | 3 | 3 | 0 / 0 / 0 | 0 / 0 (empty) | 0 | 0 | False |
| c5b6605346c90 | 0/3 | 3 | 3 | 1 / 0 / 1 | 0 / 0 (absent) | 0 | 1 | False |
| cfce8f9789f52 | 0/3 | 3 | 3 | 1 / 3 / 4 | 0 / 0 (absent) | 0 | 1 | False |
| c59e9d85be08e | 0/3 | 3 | 3 | 1 / 3 / 4 | 0 / 0 (absent) | 0 | 1 | False |
| cbe90458a394a | 0/3 | 3 | 3 | 0 / 0 / 0 | 0 / 0 (empty) | 17 | 2 | False |
| ca2634c0d43bd | 0/3 | 3 | 3 | 0 / 0 / 0 | 1 / 8 (nonempty) | 17 | 3 | False |
| c800f68970968 | 0/3 | 3 | 3 | 1 / 0 / 1 | 0 / 0 (empty) | 17 | 3 | False |
| ccc65d3bb7326 | 0/3 | 3 | 3 | 0 / 0 / 0 | 8 / 46 (nonempty) | 17 | 10 | False |
| c7e847fbdbe6d | 0/3 | 3 | 3 | 0 / 0 / 0 | 23 / 161 (nonempty) | 0 | 23 | False |

## Evidence basis

Every row links by candidate ID to `candidates/<id>/protocol.json`, exact prompt/diff/asset, and outcomes in `research-state.json`. Raw evidence: `logs/minimal-prompt-hillclimb/<id>/run-0N/`.

## Interpretation and lessons

No new outcome is inferred from absence of logs. Zero lexical additions with a link/asset change is not an unchanged task. Historical step 5 own-only is excluded; historical cohorts are never pooled. Clean cohorts require a native full tool-trace audit before provisional promotion. Legal-move enumeration and alternative evaluators remain explicit confounds. There is no held-out validation cohort or trustworthy numerical quota counter.

Stop reason: None
