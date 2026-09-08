# TouchGrass development handoff

This document is the durable context for continuing the long-running TouchGrass project on a new Mac. It summarizes the original Codex conversation and the product decisions that should survive even if the original task history is unavailable.

Last updated: 2026-09-07.

Windows handoff base before these migration files were added:

- Branch: `TouchGrass`.
- Commit: `777bcc533a3229236dfd486e2b2edc437f085973`.
- The working tree was clean before this handoff package was created.

## Start here on the new laptop

1. Read this file and `AGENTS.md` completely.
2. Confirm the current Git branch, commit, and working-tree status. Do not discard uncommitted user work.
3. Follow `documentation/docs/development/macos_setup.md`.
4. Restore the ignored migration bundle only if one was exported from Windows.
5. Read the restored UAT matrix before changing behavior.
6. Run baseline frontend and backend checks before implementing fixes.

Suggested first message to a new Codex task:

> This is the continuation of a long-running TouchGrass project. Read `AGENTS.md`, `MAC_HANDOFF.md`, and `documentation/docs/development/macos_setup.md` completely. Inspect the repository and restored UAT matrix without changing code. Confirm the development stack and baseline tests on this Mac, then give me a concise status report and the safest next P1 fix. Preserve all existing product decisions and do not contact real integrations.

## Product direction

TouchGrass began as a heavily customized branch of AdventureLog. The goal is a cohesive shared-household travel application inspired by Skylight Calendar's friendly, profile-colored interface.

Primary usage environments:

- A polished desktop/web application.
- A wall-mounted touchscreen display.
- A responsive iPhone/PWA experience.
- A privately hosted household service, eventually on a small home server or mini PC.

The interface should feel intentional at every size. Mobile support must never make desktop feel like a stretched phone layout, and wall-display support must not create tiny phone controls.

## Core information model

### Profiles

- Spencer, Ashley, and Joint are the principal household profiles.
- Every profile has its own color.
- Selected profile chips determine what the user is editing, but other profiles' travel remains visible on shared maps.
- A location may have multiple profiles and display split profile colors.
- Joint represents an explicit shared visit or shared trip.
- Spencer plus Ashley visiting independently must not automatically become Joint.
- If Joint has visited a location, Joint has visual precedence on the map. Later individual revisits remain in visit history but do not replace the Joint fill.
- Visits store profile participation so stops within one Trip can have different participants.
- Profiles and Trips can be shared with another TouchGrass login.

### Passport and Travel Map

- The former Countries page is now a broader Passport concept.
- Passport includes countries, all 50 US states, and Canadian provinces.
- Search is universal across countries/states/provinces and provides typeahead suggestions.
- World flags display visited/unvisited state efficiently; flag loading was optimized and should not regress.
- Completed accepted Visits drive country/state/province counts and polygon fills.
- Raw GPS points, candidates, future visits, saved Places, and indexed photos never fill polygons.
- US states remain individually visible even when zoomed out; the US does not receive a single whole-country fill.
- Canadian provinces behave similarly and remain visible without filling all of Canada.
- Other countries should not show their internal administrative subdivisions.
- Map labels use two-letter country codes; the US uses two-letter state abbreviations instead of a US label.
- Other profiles' fills and labels remain visible when one profile is selected.
- Country geometry should use mainland-focused behavior for visit fills while still preserving real land on the base map.
- The map must not wrap into repeated worlds.
- Search focus outlines must clear when selection is cleared or replaced.
- Click edits the selected profile; a context action/long-press opens detailed inspection.
- State/province inspectors must show that exact subdivision's profiles, history, dates, and Trip links—never all parent-country history.

### Trips

- Trips store past, current, and future journeys persistently.
- Multiple profiles can participate in one Trip.
- Trips contain sequential countries/states/provinces/places and dated Visits.
- Skylight Calendar is a source of planned/manual trip information, but calendar events require classification before becoming Trips.
- Work trips, Home events, birthdays, and ordinary family visits are excluded from trip detection.
- Existing accepted Trips must not remain in the Skylight suggestion queue.
- Review/classification notes are private classifier evidence and must not become public Trip notes or visit-history descriptions.
- Examples used during classification included Austin as a real trip, Trigon Retreat in Charlottesville, skiing in Canaan Valley, and a five-week Europe journey. These examples guide classification but must not be hardcoded as general rules.
- The Europe example is one continuous journey: France and Spain may be Joint; Switzerland, London, and Amsterdam may be Spencer-only.
- Trip cards should use the same shared visual structure for upcoming, past, and suggested trips.
- Registered cards do not need redundant Coming up/Completed bubbles because their sections provide that context.
- Destination chips are restrained neutral outlined elements rather than competing profile colors.
- Trip actions remain bottom-aligned regardless of notes/title/destination length.
- Current Trip planner pages use an optional Google Docs link stored in the collection `link` field.
- Google Doc URLs are normalized; embedded editing is best-effort and Open in Google Docs is always available.
- TouchGrass Trip sharing does not grant Google Doc permission.
- TouchGrass trip pages show Planner; Photos is enabled as its own view as integration work progresses.
- Generic non-Trip AdventureLog collections retain their original collection behavior.

### Places and Visits

- AdventureLog `Location` is the permanent accepted Place record.
- Places have Saved, Upcoming, and Visited states derived from Visits.
- Places support typeahead search, facets, profile/category/geography/Trip/date/source filters, sorting, pagination, preview sheets, and detail pages.
- Visits support start and end dates, profiles, optional linked Trip, and source.
- Place preview sheets have one scroll owner and must close with Escape and restore focus.
- Accepted Places may appear as map markers. Raw telemetry never appears on the main map.
- Duplicate-place merging must preserve visits, media, collections, and trips.

### Ballparks

- The MLB view uses all 30 current MLB parks, including Toronto with a small portion of Canada visible.
- Every team has its own logo marker.
- Every marker has a leader line to the real stadium location, visited or not.
- Leader-line colors are neutral and must not change when selected profiles change.
- Profile selection determines whose ballpark visit is edited.
- The only required statistic is `x/30 parks visited`.

## Visual language

- The design is inspired by Skylight Calendar, but tokens/components are native to this project.
- Shared tokens live in `frontend/src/lib/styles/touchgrass-tokens.css`.
- Profile selectors should use one shared component and match the Ballparks version: colored profile chips, selected outline, and a transparent `+ Profiles` action without a colored bubble.
- Navigation has Home, Passport, Travel Map, Places, Trips, and Ballparks. Legacy Locations, Collections, Calendar, and Users remain feature-hidden.
- The active navigation item uses the theme-appropriate action color; avoid dots or ornamental underlines.
- Navigation progress is a thin Material-style indeterminate dash attached to the bar. It grows, shrinks, and travels while navigation is active, then disappears immediately. Reduced motion should use a stationary opacity pulse.
- Profile dropdowns and side sheets must be opaque, correctly stacked, theme-aware, and must not darken the whole page unless a modal interaction specifically requires it.
- Maintain readable contrast across Light, Night, Forest, Aesthetic Light/Dark, and other supported themes.
- Toast close buttons remain in a fixed position regardless of message length.
- Avoid duplicate scrollbars when a drawer or sheet is open.

## Integrations

### Skylight

- TouchGrass uses the unofficial `@kamilio/skylight-calendar-agent` OAuth approach, not the earlier HAR-capture experiment.
- OAuth credentials are encrypted in backend storage.
- The Trips page owns calendar name, last checked time, sync, event review, suggestions, and operational status.
- Settings owns connect/disconnect and the collapsed Who is who mapping.
- Skylight `Joint` maps to the TouchGrass Joint profile, not Spencer plus Ashley.
- Trip detection uses dates, locations, title/description signals, prior ground-truth decisions, and duplicate matching. It does not treat every calendar event as a trip.
- Only likely Trips within all past dates plus approximately three months ahead should enter the normal review window.

### OwnTracks and automatic location tracking

- OwnTracks is the planned first iPhone collector. TouchGrass receives pushes; the PWA does not claim reliable background tracking.
- Each phone maps to exactly one individual profile, never Joint.
- Tokens are per-device, revocable, and stored hashed. HTTP Basic is accepted only over private Tailscale HTTPS.
- Home starts as a 500-meter privacy zone. Exact coordinates inside privacy zones are discarded after containment checks.
- Raw samples are separate from AdventureLog Places and have limited retention.
- Samples become stay candidates, journeys, review suggestions, accepted Places/Visits, and optionally Trips only after user approval.
- Never automatically create a permanent Trip or change Passport/map fills from telemetry.
- Joint evidence may be suggested from overlapping Spencer/Ashley devices but requires sufficient evidence or confirmation.
- Tailscale Serve, not Funnel, is the intended private ingress.

### iCloud Photos

- The implemented Windows poller scans `C:\Users\spenc\iCloudPhotos\Photos` using `os.scandir`, SQLite checkpoints, ExifTool, JSON batches, and Windows DPAPI.
- It indexes metadata and relative paths; it does not copy originals into AdventureLog media.
- Reading cloud-only Windows placeholders may cause iCloud to hydrate/download originals. This previously contributed to disk pressure and must remain throttled.
- Originals are mounted read-only into Docker. Browser-compatible previews are disposable, bounded cache files.
- Photo metadata never alters map fills, Places, Visits, or Trips automatically.
- Strong unique Trip matches may be linked; ambiguous/date-only matches require review.
- The source is Spencer-only; Ashley's photo library is not available.
- The current poller cannot run unchanged on macOS because it relies on DPAPI, Task Scheduler, and the Windows iCloud folder model. Do not copy its encrypted configuration. Re-pair or design a macOS adapter later.

### Other integrations

- Immich, Google Maps, Strava, Wanderer, OwnTracks, iCloud Photos, and Skylight use a consistent integration-card shell and status treatment.
- Owner-only integration configuration and sensitive diagnostics must never be visible to ordinary household members.

## Current implementation landmarks

- Development Compose: `docker-compose.dev.yml`, frontend 8015 and backend 8016.
- Isolated UAT Compose: `docker-compose.uat.yml`, frontend 8115 and backend 8116.
- Frontend: SvelteKit/Svelte 4 under `frontend/`.
- Backend: Django/PostGIS under `backend/server/`.
- Travel map assets: `frontend/static/geo/` and `frontend/map-source/`.
- TouchGrass components: `frontend/src/lib/components/touchgrass/`, `travel/`, and `trips/`.
- UAT harness: `uat/` and `scripts/uat/`.
- Windows iCloud poller: `tools/icloud-poller/`.
- Feature documentation: `documentation/docs/configuration/` and `documentation/docs/design/touchgrass_ui.md`.

## Useful upstream and design references

- Original application: `seanmorley15/AdventureLog`. Existing Trip, Location, Visit, collection, image, Immich, and map behavior should be reused when it fits rather than recreated blindly.
- Skylight visual reference: `mohesles/my-skylight-calendar`. It was useful as inspiration, but most TouchGrass tokens/components are project-native because that repository did not contain a complete cloneable design system.
- Scratch-map inspiration: `ad3m3r5/scratch-map`, especially compact profile-colored geographic badges.
- Boundary data: Natural Earth 10m country data and geoBoundaries CGAZ were used to improve map geometry. Runtime map assets are compact files committed under `frontend/static/geo/`; do not depend on the old Windows Downloads paths.
- MLB source: `cageyjames/GeoJSON-Ballparks`, filtered to MLB parks only.
- Stadium layout reference: the original `stadiums.jpeg`/`stadiums.jpg` in the Windows Downloads folder used offset logos with arrow/leader lines. That local reference image is not guaranteed to exist on the Mac.
- Trip animation inspiration: D3/Observable world-tour style chronological routes, only when a user opens a Trip and chooses to play it.

## Completed UAT program

An isolated six-persona UAT program was implemented and executed:

- A: desktop household owner.
- B: iPhone household member.
- C: travel-data consistency reviewer.
- D: mocked integration/failure-state reviewer.
- E: accessibility/theme/resilience reviewer.
- F: outsider access-control reviewer.

Final result:

- 44 total scenarios.
- 24 Pass.
- 17 Fail.
- 3 Blocked by harness limitations.
- 0 Untested.

The ignored evidence folder should be transferred separately from Windows. The principal report is:

`.uat-artifacts/reset-20260901-183913/agent-reports/consolidated-44-scenario-matrix.md`

The detailed browser summary is:

`.uat-artifacts/reset-20260901-183913/agent-reports/agent-driven-browser-uat-final.md`

## Open release blockers

P1 priorities:

1. California/state inspection briefly shows United States-level Joint controls and history before subdivision data settles. Actions must be disabled or state-correct from the first interactive frame.
2. Place Visit creation can send a nonexistent seeded profile ID and return HTTP 400.
3. The expected pending Skylight suggestion can be absent even when the baseline manifest expects it.
4. Household members can see owner-only OwnTracks Home coordinates, iCloud pairing, and other integration management controls.
5. When the backend is unavailable, Trips can display Login/Signup, zero trips, and disconnected Skylight instead of an error/unavailable state.

Known P2 issues:

- Google Doc Remove can emit no request.
- Trip photo Unlink can emit no request.
- Place preview ignores Escape and fails focus restoration.
- Mobile navigation trigger lacks an accessible name and Escape dismissal.
- Reduced-motion navigation still runs the traveling/growing dash.
- Aesthetic Dark active navigation text has inadequate contrast.
- Places can briefly render accepted records with zero statistics before statistics settle.

Harness-blocked manual tests:

- Native iPhone long-press.
- Genuine browser zoom at 200 percent.
- Full accepted-Place chronological Trip-route rendering with a suitable fixture.

## Migration boundaries

The Git clone contains only committed repository files. It does not contain:

- `.env` or `.env.uat.local`.
- PostgreSQL data in Docker volumes.
- AdventureLog media volume contents.
- `.uat-artifacts` evidence.
- Photo preview cache (disposable and should not be transferred).
- Node/pnpm caches (disposable and should not be transferred).
- Windows DPAPI poller credentials (not portable and should not be transferred).
- Docker Desktop settings or raw Linux VM disk (do not transfer).

Use `scripts/migration/Export-TouchGrassForMac.ps1` on Windows and `scripts/migration/Restore-TouchGrassOnMac.sh` on the Mac. The export uses `pg_dump`, not a raw Postgres volume copy, so it remains portable across operating systems and CPU architectures. The default bundle excludes `.env` and the media-volume Skylight credential key; reconnect integrations on the Mac. Use `-IncludeSecrets` only for a deliberately private transfer when preserving those credentials is necessary.

Migration bundles are deliberately gitignored and may contain private travel data. Never add them to GitHub.

## Historical implementation pitfalls

- Compose service names are `web`, `server`, and `db`. Use `docker compose ... exec server`, not the container display name `adventurelog-backend` as a service argument.
- Docker errors involving `dockerDesktopLinuxEngine`, `docker.sock`, API 500 responses, or a missing named pipe usually mean Docker Desktop is stopped or unhealthy—not a TouchGrass application defect.
- Docker Desktop previously exhausted the Windows disk. Large contributors included Docker images/build cache plus iCloud placeholder hydration. The poller does not intentionally copy every photo into TouchGrass, but reading cloud-only iCloud files can download them locally.
- Never migrate Docker Desktop's raw VM disk or the raw Postgres volume to the Mac. Use this handoff's `pg_dump` archive.
- Windows/OneDrive bind mounts can lose filesystem events. The development Compose file enables Vite polling to compensate. This may be unnecessary on the Mac but is safe to leave initially.
- The frontend stack is Svelte 4. TypeScript annotations such as `(feature:any)` and `as typeof ...` inside Svelte template expressions have caused parser errors; move typed expressions into the script block.
- Browser-only libraries must be guarded during SSR. `localStorage.getItem is not a function` previously came from importing the Umami package on the server.
- Transparent menus/sheets repeatedly resulted from stacking-context and theme-surface drift. Reuse shared opaque surface tokens/components; do not solve one route with an isolated z-index patch.
- Map layers previously disappeared or lost fills during rapid profile switching/zoom. Preserve stable source/layer identity, avoid rebuilding large GeoJSON unnecessarily, and keep profile membership separate from the active editing profile.
- Country ISO alpha-2 badges are intentional (`CH` Switzerland, `AW` Aruba, `DO` Dominican Republic). US labels are state codes instead of a country badge.
- Country fills deliberately focus on the principal mainland polygon, but the neutral base map must still show islands and detached land such as Alaska or Corsica. Do not delete land geometry merely to control visit highlighting.
- The UAT continuation PowerShell loop encountered corrupted resumed Codex sessions with missing tool-call outputs. It was made to discard bad session IDs and preserve progress in the artifact matrix. The completed run has a `.uat-artifacts/automation/STOP` marker; do not restart it automatically on the Mac.
- The six-agent UAT program was evidence-only. Do not edit source code while running those charters, and reset isolated fixtures between destructive persona journeys.

## Definition of a safe continuation

Before new feature development:

- Restore or freshly initialize the Mac development stack.
- Confirm database migrations.
- Confirm Home, Passport, Travel Map, Places, Trips, Ballparks, and Settings load.
- Run frontend `svelte-check`.
- Run targeted backend tests.
- Keep real Skylight, OwnTracks, Google, and photo ingestion disabled until local functionality is confirmed.
- Fix/retest P1 findings before expanding automatic tracking or media features.
