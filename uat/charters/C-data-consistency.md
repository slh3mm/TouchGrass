# Agent C — Travel-data consistency reviewer

Use `uat-owner` at 1440×900. Run `DASH-001`, `PASS-001` through `PASS-005`, `MAP-001` through `MAP-005`, `PLACE-001` through `PLACE-004`, `TRIP-002`, `BALL-002`, and `PERF-001`.

Compare Home, Passport, Travel Map, Places, Trips, and Ballparks before and after each mutation. Confirm state-specific history, explicit Joint precedence, preservation of later individual visits, exclusion of candidates/future visits from fills, duplicate suggestion suppression, search-clear behavior, zoom-boundary geometry, and refresh persistence. Stress actions in short bursts but create only `[UAT-C]` records.
