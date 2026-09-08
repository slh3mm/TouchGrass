# TouchGrass UAT coordinator guide

This directory defines black-box user-acceptance testing for TouchGrass. Testers look for missing, broken, confusing, inaccessible, slow, or inconsistent behavior. They report findings; they never repair application code during a UAT run.

## Safety rules

- Use only the disposable UAT URL and accounts from the generated manifest. Never use ports 8015 or 8016.
- Never enter production Apple, OwnTracks, Google, Skylight, Immich, Strava, or Wanderer credentials.
- Do not include passwords, tokens, exact Home coordinates, absolute photo paths, or private calendar text in evidence.
- Prefix every created record with the agent prefix `[UAT-A]` through `[UAT-F]`.
- Stop immediately on a P0 security or data-loss finding and preserve the current database and browser state.

## Required environments

| Name | Browser profile | Viewport | DPR | Input |
| --- | --- | ---: | ---: | --- |
| Desktop | Chromium | 1440 × 900 | 1 | Mouse and keyboard |
| iPhone portrait | Mobile emulation | 393 × 852 | 3 | Touch |
| iPhone landscape | Mobile emulation | 852 × 393 | 3 | Touch |
| Accessibility zoom | Chromium at 200% zoom | 1280 × 720 | 1 | Keyboard only |

The initial run excludes the wall-display viewport. That charter remains documented for a later release gate.

## Serial run protocol

1. Create a run ID in the form `YYYYMMDD-HHMM-commitShortSha`.
2. Record the commit, browser version, UAT seed version, base URL, and manifest checksum.
3. Verify the UAT base URL is `http://localhost:8115` and the health/manifest checks pass.
4. Run one browser tester at a time because browser storage and mutable records must not overlap.
5. Run A, reset, B, reset, C, reset, D, reset, E, reset, then F.
6. Before each tester, log out, clear TouchGrass cookies and local storage, select Light theme, and close all open drawers/dialogs.
7. The tester writes findings and a summary only. The coordinator validates and deduplicates them.
8. For the coordinated owner/member sequence, do not reset between the two accounts; reset immediately afterward.
9. Apply the release rules in `matrix.md`, then hand the human checklist to Spencer.

Raw evidence belongs in `.uat-artifacts/<run-id>/<agent>/`. It is ignored by Git. A sanitized summary may be copied into `uat/reports/` only after checking it contains no private data.

## Results and severity

- **Pass:** every expected result was observed.
- **Fail:** a reproducible product finding exists.
- **Blocked:** the environment or fixture prevented the scenario.
- **Not run:** no attempt was made; this is never equivalent to Blocked.

- **P0:** unauthorized access, unrecoverable corruption/data loss, or the app is unusable for all testers.
- **P1:** a core journey is blocked, persisted data is wrong, or travel/profile security is materially incorrect.
- **P2:** substantial degradation with a workaround, stale state fixed by refresh, or an important mobile/accessibility failure.
- **P3:** low-impact visual, spacing, wording, or polish issue.

Classify by user impact, not guessed implementation cause. A missing feature is an expected capability that is absent; a bug is an existing capability behaving incorrectly. Merge the same symptom across devices into one finding with multiple evidence entries.

Performance thresholds: P1 when interaction is unavailable for more than 10 seconds or a data action times out; P2 when a primary route takes more than 5 seconds to become interactive or mutation feedback takes more than 2 seconds.

## Finding evidence

Every failed scenario needs a JSON finding conforming to `schemas/finding.schema.json`, including exact steps, expected and actual behavior, reproduction count, screenshot, and console/network/server evidence when relevant. Each tester also completes `templates/agent-summary.template.md` and lists every created or modified record.

## Agent charters

- A: desktop household owner
- B: shared household member on an iPhone-sized viewport
- C: travel-data consistency and cross-page correctness
- D: mocked integrations and failure states
- E: accessibility, themes, performance, and resilience
- F: outsider access-control boundaries

The scenario source of truth is `scenarios.json`; charters select a subset rather than redefining expected behavior.
