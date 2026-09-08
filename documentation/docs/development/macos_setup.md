# Continue TouchGrass development on macOS

This guide assumes the repository is already cloned on the Mac.

## Requirements

- Current Docker Desktop for Mac with Docker Compose v2.
- Git.
- At least 25 GB of free disk space before building images and restoring data; more is recommended if media is included.
- On Apple Silicon, allow Docker to use arm64 images normally. Do not copy Docker Desktop's Windows VM disk or raw Postgres volume.

Node and Python do not have to be installed on the host for the normal Compose workflow, although local tooling can be useful.

## Prepare configuration

1. Copy `.env.example` to `.env` if no private `.env` was restored.
2. Replace every sample password/key. Preserve a restored `SECRET_KEY` if continuity is required.
3. Keep these development defaults unless there is a concrete reason to change them:

   - `PUBLIC_SERVER_URL=http://server:8000`
   - `ORIGIN=http://localhost:8015`
   - `PUBLIC_URL=http://localhost:8016`
   - `FRONTEND_URL=http://localhost:8015`
   - `CSRF_TRUSTED_ORIGINS=http://localhost:8016,http://localhost:8015`
   - `ALLOWED_HOSTS=localhost,127.0.0.1,server`

4. The Windows iCloud path is invalid on macOS. Create the harmless empty local directory used by the default read-only mount until a Mac photo collector is intentionally configured:

```bash
mkdir -p .local/icloud-photos
```

Set `ICLOUD_PHOTOS_ROOT=./.local/icloud-photos` in `.env`, or omit the variable and use the same Compose fallback. Do not point it at the macOS `Photos Library.photoslibrary` package.

Existing indexed photo metadata restored from Windows will remain visible, but the originals will correctly appear unavailable until a future Mac-compatible collector is paired. This does not affect Trips, Places, Passport counts, or map fills.

5. Do not copy the Windows poller's `%LOCALAPPDATA%` configuration. Its token is encrypted with Windows DPAPI and cannot be decrypted on the Mac.

## Restore a Windows migration bundle

Transfer the generated `.zip` privately using an encrypted drive, AirDrop, or another trusted channel. Do not upload it to the repository.

From the repository root:

```bash
chmod +x scripts/migration/Restore-TouchGrassOnMac.sh
scripts/migration/Restore-TouchGrassOnMac.sh /path/to/touchgrass-mac-transfer-YYYYMMDD-HHMMSS.zip
```

The safe default expects a fresh database and does not erase existing records. Use `--replace-existing` only when intentionally replacing a disposable/new Mac database with the Windows dump.

If the bundle does not contain `.env`, create it from `.env.example`. This is the default because secrets should not be placed into an ordinary archive. The default export also excludes the media-volume Skylight credential key, so reconnect Skylight after restore. A deliberate `-IncludeSecrets` Windows export preserves both when transferred through a secure private channel.

## Start development

```bash
docker compose -f docker-compose.dev.yml up -d --build
docker compose -f docker-compose.dev.yml ps
docker compose -f docker-compose.dev.yml logs --tail=100 server web
```

Open `http://localhost:8015`.

Apply/check migrations explicitly if needed:

```bash
docker compose -f docker-compose.dev.yml exec server python manage.py migrate
docker compose -f docker-compose.dev.yml exec server python manage.py showmigrations
```

## Baseline verification

Frontend:

```bash
docker compose -f docker-compose.dev.yml exec web pnpm check
```

Backend targeted tests should run inside `server`; start with the applications touched by the next change rather than assuming the full inherited AdventureLog suite is fast or clean.

Check these pages manually:

- Home
- Passport
- Travel Map
- Places
- Trips and one planner
- Ballparks
- Settings and profile menu
- One phone-size viewport
- One dark theme

## Restore UAT evidence

If `.uat-artifacts.tar.gz` was included in the transfer, the restore script places it back at `.uat-artifacts/`. It remains gitignored. Read the latest consolidated matrix before fixing defects.

The isolated stack is separate from development:

```bash
docker compose -f docker-compose.uat.yml up -d --build
```

Use only ports 8115/8116 for UAT. Never run test agents against the normal 8015/8016 data.

## First Codex task

Open this repository as the Codex project and use:

> Read `AGENTS.md`, `MAC_HANDOFF.md`, and `documentation/docs/development/macos_setup.md` completely. Inspect the working tree, current Compose health, migrations, and restored UAT matrix without changing code. Do not contact real integrations. Run the baseline checks that are safe on this Mac, report any migration differences, and recommend the smallest P1 fix to tackle first.

Repository `AGENTS.md` is intentionally concise and authoritative. Update `MAC_HANDOFF.md` when major product decisions change so future tasks do not depend on inaccessible chat history. Official OpenAI guidance emphasizes that agent instruction files can materially affect behavior, so keep them explicit and free of contradictory rules.
