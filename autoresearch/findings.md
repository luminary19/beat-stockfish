# Campaign leaderboard

Status: running

3/3 is exploratory/provisional, not robust. Missing/partial/error ≠ clean. No wholly-unaided claim. Costs include file titles and link targets.

| Candidate | Clean / 3 | Engine use | Valid complete | Added / deleted / edit | File words / bytes | Markup bytes | Total new lexical | Provisional |
|---|---:|---:|---:|---|---|---:|---:|---|
| cb82dd8fdde41 | 3/3 | 0 | 3 | 0 / 0 / 0 | 6 / 38 (nonempty) | 17 | 8 | True |
| c4ca75cf1dc18 | 3/3 | 0 | 3 | 0 / 0 / 0 | 7 / 42 (nonempty) | 17 | 9 | True |
| c03b1ccded318 | 3/3 | 0 | 3 | 0 / 0 / 0 | 11 / 66 (nonempty) | 17 | 13 | True |
| cf5a339b0cd90 | 3/3 | 0 | 3 | 0 / 0 / 0 | 14 / 96 (nonempty) | 17 | 16 | True |
| c398e61a30e0a | 3/3 | 0 | 3 | 0 / 0 / 0 | 23 / 161 (nonempty) | 17 | 25 | True |
| cc67bf0fac887 | 3/3 | 0 | 3 | 0 / 0 / 0 | 3 / 19 (nonempty) | 17 | 5 | False |
| cad474ffcc205 | 3/3 | 0 | 3 | 0 / 0 / 0 | 5 / 33 (nonempty) | 17 | 7 | False |
| c79f4ca65685d | 3/3 | 0 | 3 | 0 / 0 / 0 | 6 / 38 (nonempty) | 17 | 8 | False |
| c621fe189eb68 | 3/3 | 0 | 3 | 0 / 0 / 0 | 7 / 42 (nonempty) | 17 | 9 | False |
| cb95e2979d94a | 3/3 | 0 | 3 | 0 / 0 / 0 | 8 / 48 (nonempty) | 17 | 10 | False |
| c26bad62367ba | 3/3 | 0 | 3 | 0 / 0 / 0 | 8 / 48 (nonempty) | 17 | 10 | False |
| c53b68ba22d7f | 3/3 | 0 | 3 | 0 / 0 / 0 | 11 / 66 (nonempty) | 17 | 13 | False |
| c927631e2b628 | 2/3 | 1 | 3 | 0 / 0 / 0 | 4 / 28 (nonempty) | 17 | 6 | False |
| c576e11754d0c | 2/3 | 1 | 3 | 0 / 0 / 0 | 5 / 34 (nonempty) | 17 | 7 | False |
| c86889511725d | 2/3 | 1 | 3 | 0 / 0 / 0 | 13 / 92 (nonempty) | 17 | 15 | False |
| c426be3c4660d | 1/3 | 2 | 3 | 0 / 0 / 0 | 13 / 92 (nonempty) | 17 | 15 | False |
| cb5d7952a9c16 | 0/3 | 3 | 3 | 0 / 0 / 0 | 0 / 0 (empty) | 0 | 0 | False |
| c5b6605346c90 | 0/3 | 3 | 3 | 1 / 0 / 1 | 0 / 0 (absent) | 0 | 1 | False |
| cfce8f9789f52 | 0/3 | 3 | 3 | 1 / 3 / 4 | 0 / 0 (absent) | 0 | 1 | False |
| c59e9d85be08e | 0/3 | 3 | 3 | 1 / 3 / 4 | 0 / 0 (absent) | 0 | 1 | False |
| cbe90458a394a | 0/3 | 3 | 3 | 0 / 0 / 0 | 0 / 0 (empty) | 17 | 2 | False |
| ca2634c0d43bd | 0/3 | 3 | 3 | 0 / 0 / 0 | 1 / 8 (nonempty) | 17 | 3 | False |
| c612e6b2ed384 | 0/3 | 3 | 3 | 0 / 0 / 0 | 1 / 10 (nonempty) | 17 | 3 | False |
| cf19c35ab4de1 | 0/3 | 3 | 3 | 0 / 0 / 0 | 1 / 10 (nonempty) | 17 | 3 | False |
| c800f68970968 | 0/3 | 3 | 3 | 1 / 0 / 1 | 0 / 0 (empty) | 17 | 3 | False |
| cce5747c015a7 | 0/3 | 3 | 3 | 0 / 0 / 0 | 2 / 15 (nonempty) | 17 | 4 | False |
| ca9bc8571c261 | 0/3 | 3 | 3 | 0 / 0 / 0 | 4 / 29 (nonempty) | 17 | 6 | False |
| ccc65d3bb7326 | 0/3 | 3 | 3 | 0 / 0 / 0 | 8 / 46 (nonempty) | 17 | 10 | False |
| c91be84043ecf | 0/3 | 3 | 3 | 0 / 0 / 0 | 12 / 88 (nonempty) | 17 | 14 | False |
| c7e847fbdbe6d | 0/3 | 3 | 3 | 0 / 0 / 0 | 23 / 161 (nonempty) | 0 | 23 | False |

## Evidence basis

Every row links by candidate ID to `candidates/<id>/protocol.json`, exact prompt/diff/asset, and outcomes in `research-state.json`. Raw evidence: `logs/minimal-prompt-hillclimb/<id>/run-0N/`.

## Interpretation and lessons

No new outcome is inferred from absence of logs. Zero lexical additions with a link/asset change is not an unchanged task. Historical step 5 own-only is excluded; historical cohorts are never pooled. Clean cohorts require a native full tool-trace audit before provisional promotion. Legal-move enumeration and alternative evaluators remain explicit confounds. There is no held-out validation cohort or trustworthy numerical quota counter.
