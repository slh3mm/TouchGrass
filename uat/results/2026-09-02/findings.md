# Prioritized UAT findings

## P1 — release blockers

### `UAT-C-001` — stale parent-country controls in state inspector

- Scenarios: `PASS-003`, `MAP-005`.
- Route: Passport/Travel Map subdivision inspector.
- Actual: California first shows United States-level identity, Joint state, controls, and history for roughly 1.2 seconds before California data replaces it.
- Required fix: keep actions disabled behind loading or render state-correct data from the first interactive frame.

### Setup `UAT-A-001` — Place Visit creation uses invalid profile ID

- Scenario: `PLACE-004`.
- Actual: Add Visit failed three times with HTTP 400 because the selected seeded profile primary key did not exist.
- Required fix: resolve accessible profile IDs from live data and stabilize stale selections before submission.

### Reset `UAT-A-002` — pending Skylight suggestion missing

- Scenario: `TRIP-002`.
- Actual: the clean baseline expected one pending suggestion; Trips rendered zero.
- Required fix: reconcile review filtering and existing-Trip suppression without hiding a genuinely pending event.

### `UAT-B-001` — member sees owner-only integration controls

- Scenarios: `SHARE-002`, `SEC-001`.
- Actual: the household member saw OwnTracks Home coordinates, iCloud owner selection/pairing, and other owner controls.
- Required fix: enforce permission server-side and omit sensitive data/controls from member payloads and UI.

### `UAT-D-001` — API failure presented as empty/logged-out data

- Scenarios: `DASH-001`, `RES-001`.
- Actual: a backend outage displayed Login/Signup, zero Trips, empty states, and Connect Skylight.
- Required fix: preserve known authentication context and show explicit unavailable/retry state.

## P2 — substantial defects

- Setup `UAT-A-003` (`TRIP-003`): Google Doc Remove emitted no request and left the link connected.
- Setup `UAT-A-004` (`TRIP-004`): photo Unlink emitted no request and left the item attached.
- `UAT-E-001` (`PLACE-003`, `MOBILE-002`, `A11Y-001`): Place preview ignored Escape and failed focus restoration.
- `UAT-B-003` (`MOBILE-001`, `A11Y-001`): mobile menu trigger was unnamed and Escape did not close it.
- `UAT-E-002` (`A11Y-003`): reduced motion still ran the traveling/growing loader.
- `UAT-E-003` (`G-003`): Aesthetic Dark active navigation text lacked contrast.
- Reset `UAT-A-001` (`PERF-001`): Places rendered records with zero statistics for roughly 2.8 seconds.

## Closed/cannot reproduced

- Setup `UAT-A-002`: Trip Delete is now discoverable; disposable lifecycle fixture was cleaned.
- `UAT-B-002`: member saw 6 upcoming and 104 past Trips and opened a shared planner/editor.

## Required manual checks

- Native iPhone long-press on map state/country targets.
- Genuine 200% browser zoom across primary routes.
- Full accepted-Place marker and chronological selected-Trip route using a purpose-built non-private fixture.
