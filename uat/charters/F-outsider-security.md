# Agent F — Outsider access-control reviewer

Use `uat-outsider` on desktop. Run `G-001`, `SEC-001`, `SHARE-002`, `TRIP-005`, and `PHOTO-001` using IDs supplied in the sanitized manifest.

Attempt direct reads and safe, reversible mutations against private profiles, Trips, collections, photos, Places, and suggestions. Confirm no object names, metadata, images, IDs beyond the attempted URL, or write capability leaks. Treat expected 401/403/404 results as passes. On any unauthorized success, stop immediately and file a P0 without attempting further access.
