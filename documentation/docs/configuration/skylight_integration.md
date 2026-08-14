# Skylight calendar integration

TouchGrass can connect to a Skylight calendar, scan calendar events for likely
trips, and present them for approval on the Trips page. Imported events never
become TouchGrass trips until a user accepts the suggestion.

The implementation follows the OAuth flow and read-only endpoints exposed by
`@kamilio/skylight-calendar-agent`. The npm package is a protocol reference,
not a production subprocess or runtime dependency, and TouchGrass does not need
a HAR file after setup.

## Credential encryption

Skylight OAuth access and refresh tokens are encrypted in PostgreSQL with
authenticated Fernet encryption. Tokens are never returned to the frontend and
are never written to browser storage.

For the local Docker setup, TouchGrass creates a mode-`0600` Fernet key at
`MEDIA_ROOT/.skylight-credential-key` on first use. That path lives in the
persistent `adventurelog_media` Docker volume, not in the Git worktree. This is
the appropriate local arrangement because the backend runs inside Linux Docker
and cannot safely depend on the host's Windows Credential Manager or DPAPI.

For a deployed or multi-host installation, set a dedicated encryption key in
`.env` or inject it through your secret manager:

```powershell
docker compose -f docker-compose.dev.yml exec server python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Copy the generated value into `.env` without quotes:

```dotenv
SKYLIGHT_CREDENTIAL_KEYS=generated_value_here
```

Restart the backend after changing the key. Do not lose it: encrypted Skylight
credentials cannot be recovered without it. A deployment may alternatively
mount a secret file and set `SKYLIGHT_CREDENTIAL_KEY_FILE` to its absolute path.

To rotate keys, generate a new one and keep the old key after it:

```dotenv
SKYLIGHT_CREDENTIAL_KEYS=new_key,old_key
```

New credentials use the first key and existing credentials can still be read
with either key. Reconnect Skylight to re-encrypt the credential under the first
key, then remove the old key.

## Connect and sync

1. Open **Trips**, enter the Skylight account email and password, and choose
   **Connect securely**. TouchGrass submits them directly to Skylight, discards
   them immediately, and retains only the encrypted OAuth credential.
2. If Skylight requires device or two-factor verification, use **browser login
   instead** as the one-time fallback.
5. Verify the category mappings. `Joint Events` maps to the single `Joint`
   TouchGrass profile, not to Spencer and Ashley separately.
6. Choose **Check for trips** and review each suggestion.

For classification work, choose **Review every event** on the Trips page. The
temporary review lab stores every event returned by the sync, including events
the detector believes are not trips. Each event can be marked **Trip**, **Not a
trip**, or returned to **Unreviewed**, with an optional human note. Calendar
metadata and classifier scores update during later syncs, but human labels and
notes are deliberately stored separately and are never overwritten by a
refresh. Search, filters, and 40-event pages keep the full calendar review
usable without rendering hundreds of cards at once. The lab includes all
available past events and only the next three calendar months. Events farther
in the future remain stored (so existing labels are safe) but stay hidden until
they enter that window. This wider historical scan updates only the ground-truth
lab; it does not flood the normal Trips suggestion queue with old events.

TouchGrass also performs a quiet check when a connected user opens Trips and
the previous sync is more than 15 minutes old. This is intentionally
stale-aware: opening or refreshing the page repeatedly does not hammer
Skylight, and individual calendar events never produce immediate prompts.

The detector scores each mapped event using explicit trip language, country,
state/province and city names from TouchGrass's geography database, flag emoji,
all-day duration, and any supplied location. It subtracts confidence for
recurring events, short timed appointments, local-event language, and planning
tasks such as “finish itinerary” or “look at travel insurance.” The event's own
Skylight timezone is used so an evening event cannot become an apparent
two-day event merely because UTC crosses midnight.

TouchGrass's household policy deliberately excludes the Skylight **Work
Travel** category, explicitly named work/recruiting travel, titles beginning
with **Home for**, and titles that clearly describe a family visit or family
gathering. A generic friend visit such as “Matt Visit in NYC” remains eligible.
The `YAR` shorthand is treated as trip language, while titles such as “trip ft”
are treated as a FaceTime/planning event. Destinations learned from a single
ground-truth note are not generalized to unrelated future trips—for example,
one ski trip's destination does not become the destination of every ski trip.

Each suggestion shows why it qualified. Dismissed suggestions remain dismissed
on later syncs, and accepted events cannot create duplicate trips because their
Skylight event IDs are stored uniquely.

OAuth access tokens refresh automatically with the encrypted refresh token.
The user normally signs in only once and must repeat login only if Skylight
revokes or invalidates that refresh token.

Changing a category to **Ignore this category** is sticky across later syncs.
If an unaccepted suggestion stops matching a mapped profile or the trip
heuristic, it is removed from the review queue.

This integration uses undocumented Skylight endpoints and may need updates if
Skylight changes its web API.
