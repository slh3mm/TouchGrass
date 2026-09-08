# TouchGrass six-persona UAT — 2026-09-02

## Result

The isolated UAT program completed all 44 scenarios across six beta-user charters.

| Status | Count |
| --- | ---: |
| Pass | 24 |
| Fail | 17 |
| Blocked | 3 |
| Untested | 0 |
| **Total** | **44** |

Release disposition: **Fail**. Five P1 findings remain open.

Execution environment:

- Standalone `docker-compose.uat.yml`.
- Frontend `8115`, backend `8116`.
- Sanitized copied travel data plus deterministic `[UAT]` fixtures.
- No real iCloud mount or live integration access.
- Desktop owner, iPhone household member, travel-data reviewer, integration/failure reviewer, accessibility/resilience reviewer, and outsider personas.

## Complete scenario matrix

| # | Scenario | Result | Essential evidence/disposition |
| ---: | --- | --- | --- |
| 1 | `G-001` Authentication and redirects | Pass | Owner/member/outsider login, logout, redirects, and private deep links behaved correctly. |
| 2 | `G-002` Navigation, active state, loader, deep links | Pass | Desktop/phone navigation and nested refresh worked; loader appeared only during navigation. |
| 3 | `G-003` Themes, persistence, contrast | Fail | Themes persisted, but Aesthetic Dark active navigation text had inadequate contrast. |
| 4 | `G-004` Profile dropdown | Pass | Opaque, correctly stacked, dismissible, and phone-safe. |
| 5 | `DASH-001` Statistics and error distinction | Fail | Normal counts reconciled; backend failure was incorrectly shown as empty/logged-out data. |
| 6 | `PASS-001` Universal Passport search | Pass | Keyboard typeahead, Pennsylvania selection, clear, focus return, and 51 restored subdivisions verified. |
| 7 | `PASS-002` Country visit persistence | Pass | Iceland profile toggle survived switching and reload. |
| 8 | `PASS-003` US state visit/history/Trip | Fail | California briefly exposed United States-level Joint actions before state data settled. |
| 9 | `PASS-004` Canadian province workflow | Pass | Ontario history and add-to-trip completed. |
| 10 | `PASS-005` Profile lifecycle/sharing | Pass | Reversible create/edit/share/delete lifecycle and idempotent sharing completed. |
| 11 | `MAP-001` Passport/map fills and labels | Pass | California split, explicit Joint subdivisions, country fills, labels, and cross-profile visibility matched source data. |
| 12 | `MAP-002` Touch long-press/context | Blocked | Available automation could not faithfully generate native iOS long-press. |
| 13 | `MAP-003` Search outline clearing | Pass | Clear removed the California selection and returned the map to its unselected state. |
| 14 | `MAP-004` Places layer and selected-Trip route | Blocked | Baseline lacked a suitable accepted Place/Trip route fixture for a non-destructive proof. |
| 15 | `MAP-005` Joint precedence | Fail | Settled precedence was correct, but stale parent-country Joint controls were initially actionable. |
| 16 | `PLACE-001` Search/filter/sort/pagination/empty | Pass | All behaviors and explicit no-match state verified. |
| 17 | `PLACE-002` Suggestion idempotence | Pass | Accept retry created no duplicate; dismiss/always-ignore retained one final state. |
| 18 | `PLACE-003` Preview sheet | Fail | Escape did not close; explicit Close returned focus to page root instead of trigger. |
| 19 | `PLACE-004` Visit profile/date/Trip lifecycle | Fail | Add Visit returned HTTP 400 due to a nonexistent selected seeded profile ID. |
| 20 | `TRIP-001` Trip create/edit/placement | Pass | Disposable trip created and edited; Delete was discoverable; exact fixture was cleaned afterward. |
| 21 | `TRIP-002` Skylight suggestions/deduplication | Fail | Manifest expected one pending suggestion while Trips displayed zero. |
| 22 | `TRIP-003` Google Doc lifecycle | Fail | Add/replace/fallback worked; Remove emitted no request and left the link connected. |
| 23 | `TRIP-004` Trip Photos lifecycle | Fail | States/link/move worked; Unlink emitted no request and remained attached. |
| 24 | `TRIP-005` Shared editor and Google separation | Pass | Member saw 6 upcoming/104 past Trips, opened planner/editor, and saw Google permission separation. |
| 25 | `SKY-001` Skylight integration states | Pass | Connected state rendered and mock mode explicitly blocked live actions with HTTP 409. |
| 26 | `SKY-002` Ground-truth review | Pass | Unreviewed/Trips/Not trips/All filters returned 2/1/0/3 and decisions persisted. |
| 27 | `BALL-001` Ballpark optimistic persistence | Pass | Ashley Baltimore update appeared immediately and survived reload. |
| 28 | `BALL-002` Ownership and leader lines | Pass | All 30 lines persisted and remained neutral across Spencer/Ashley switching. |
| 29 | `SET-001` Settings tabs/mobile | Pass | Seven tabs worked at portrait and landscape phone sizes without page overflow. |
| 30 | `SET-002` OwnTracks lifecycle | Pass | Home/pair/pause/resume/revoke API plus UI state updates verified and restored. |
| 31 | `SET-003` iCloud index lifecycle | Pass | 1,004-item state, filters, errors, responsive layout, and pause/resume/retry verified. |
| 32 | `SET-004` Other integration cards | Pass | Immich, Google Maps, Strava, and Wanderer used consistent card/status structure. |
| 33 | `PHOTO-001` Photo index/filter/permissions | Pass | Filters/pagination/states worked; outsider and unauthenticated asset access was rejected. |
| 34 | `SHARE-001` Household sharing visibility | Pass | Member saw shared profiles/Trips and opened shared detail/editor. |
| 35 | `SHARE-002` Cross-account isolation/allowed edits | Fail | Outsider isolation passed; member could see owner-only OwnTracks/iCloud controls. |
| 36 | `MOBILE-001` Mobile/PWA navigation | Fail | Hamburger lacked an accessible name and Escape did not close the menu. |
| 37 | `MOBILE-002` Drawers/rotation/back | Fail | Portrait/landscape rendered, but Place sheet failed Escape/focus behavior. |
| 38 | `A11Y-001` Keyboard/focus/Escape | Fail | Profile menu passed; Place preview and mobile navigation failed. |
| 39 | `A11Y-002` True 200% browser zoom | Blocked | Automation could resize viewport but could not set/verify genuine browser zoom. |
| 40 | `A11Y-003` Reduced motion/announcements | Fail | Reduced motion still ran the growing/traveling navigation dash. |
| 41 | `PERF-001` Cold/warm and rapid mutation | Fail | Cold map approached six seconds; Places showed zero statistics for about 2.8 seconds before settling. |
| 42 | `RES-001` Failed API versus empty state | Fail | Backend outage displayed Login/Signup, zero Trips, and disconnected Skylight rather than an error. |
| 43 | `RES-002` Refresh/offline/recovery | Pass | Nested refresh and backend restart recovery worked. |
| 44 | `SEC-001` Deep links and access boundaries | Fail | Outsider was contained; household member could access owner-only integration controls. |

## High-confidence observations

- Passport and Travel Map membership sources agreed.
- Selecting one profile did not hide other profiles' map visits or labels.
- Spencer plus Ashley independent California evidence remained split and did not become Joint.
- Explicit Joint Ontario/Massachusetts remained Joint.
- Ballpark leader lines existed for all teams and did not inherit the selected profile color.
- Outsider direct collection/photo/Place/Trip access did not expose household data.
- Mock integrations did not contact real services.
- A controlled backend outage recovered after restart, but the failure presentation was misleading.

## Raw evidence boundary

The original supporting material remains private and gitignored at `.uat-artifacts/reset-20260901-183913/`. It includes screenshots, network/API observations, server diagnostics, synthetic fixture information, and agent reports. It is contained in the private Windows-to-Mac migration bundle but is not required to understand or prioritize the tracked results.

Do not weaken or dismiss a tracked finding merely because the raw folder is absent. Retest the exact scenario after implementing a fix and record the new result under `uat/results/`.
