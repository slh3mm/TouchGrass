# TouchGrass agent guidance

Read `MAC_HANDOFF.md` before planning or changing this repository. It records the product decisions, integrations, migration constraints, and current UAT findings from the original Windows development task.

## Working rules

- Treat TouchGrass as a shared household travel product, not a generic AdventureLog reskin.
- Desktop, wall-display, tablet, and phone layouts are all first-class. Do not fix one by degrading another.
- Preserve profile behavior for Spencer, Ashley, and Joint. Joint is explicit shared evidence; never infer it merely because Spencer and Ashley visited independently.
- Completed accepted Visits may affect Passport and map fills. Raw telemetry, photo metadata, candidates, saved Places, and future visits must not.
- US states and Canadian provinces remain individually visible and fillable. Do not reintroduce subdivisions for every country.
- Keep the streamlined TouchGrass navigation and Skylight-inspired design tokens consistent across routes.
- Keep legacy AdventureLog navigation behind its feature toggle.
- Never contact real integrations or ingest real location/photo data during automated tests.
- Never commit `.env`, credentials, database dumps, migration bundles, `.uat-artifacts`, photo previews, or iCloud originals.
- The Windows iCloud poller uses DPAPI and Task Scheduler. It cannot simply be copied to macOS; treat it as disabled until a Mac collector is designed and paired.

## Development and verification

- Use `docker-compose.dev.yml` for local development.
- Use `docker-compose.uat.yml` on ports 8115/8116 for isolated UAT. Do not point test agents at 8015/8016.
- Preserve unrelated user changes in the working tree.
- Run frontend `svelte-check` after Svelte/TypeScript work.
- Run targeted backend tests and migration checks after Django changes.
- For cross-feature changes, verify Home, Passport, Travel Map, Places, Trips, Ballparks, Settings, phone width, and at least one dark theme.
- Review the latest matrix under `.uat-artifacts/.../agent-reports/consolidated-44-scenario-matrix.md` when that ignored evidence directory has been restored.

## Current priority

Fix open P1 UAT findings before adding major new features:

1. State/province inspectors must not expose stale parent-country controls.
2. Place Visit creation must use valid profile IDs.
3. Pending Skylight trip suggestions must appear and suppress existing Trips correctly.
4. Household members must not see owner-only integration credentials or management controls.
5. Failed APIs must show an error/unavailable state instead of empty or logged-out data.

After each fix, retest the exact recorded scenario and update the UAT finding rather than assuming it is resolved.
