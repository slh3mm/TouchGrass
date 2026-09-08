# Automatic location tracking with OwnTracks

TouchGrass accepts private, location-only reports from OwnTracks and turns them into review suggestions. It does **not** import photos, store Apple credentials, or automatically create permanent Trips, Visits, Passport fills, or map fills.

## Private Tailscale HTTPS address

Install Tailscale on the TouchGrass computer and each participating iPhone, join them to the same tailnet, and expose the frontend privately:

```powershell
tailscale serve --bg localhost:8015
tailscale serve status
```

Use **Serve**, not Funnel. Serve is restricted to the tailnet; Funnel would make the endpoint public. Tailscale prints a stable address similar to `https://touchgrass.example-tailnet.ts.net`.

Update `.env` with that exact hostname:

```dotenv
ORIGIN=https://touchgrass.example-tailnet.ts.net
FRONTEND_URL=https://touchgrass.example-tailnet.ts.net
PUBLIC_URL=https://touchgrass.example-tailnet.ts.net
CSRF_TRUSTED_ORIGINS=https://touchgrass.example-tailnet.ts.net
ALLOWED_HOSTS=touchgrass.example-tailnet.ts.net,localhost,127.0.0.1,server
```

`PUBLIC_SERVER_URL` remains `http://server:8000`; it is the private Docker connection between the frontend and backend. Recreate both application services after changing origins:

```powershell
docker compose -f docker-compose.dev.yml up -d --force-recreate server web
```

## Pair an iPhone

1. Open **Settings → Integrations → Automatic location tracking**.
2. Configure the required Home privacy zone. TouchGrass discards exact samples inside this radius.
3. Map the phone to one individual profile. Do not map a phone to Joint.
4. Select Balanced, Battery saver, or Detailed travel tracking.
5. Generate the one-time setup and save it immediately; the token is stored hashed and cannot be shown again.
6. OwnTracks 26.2.2 and newer disable external configuration by default. In OwnTracks Settings, explicitly allow configuration links/files before scanning the QR code.
7. Give OwnTracks **Always** location permission. Define a Home region, use Significant mode at Home, switch to Move mode on leaving, and return to Significant mode on entering.
8. Tap the upload arrow in OwnTracks. The TouchGrass device card should change from Waiting to Connected.

Balanced config uses roughly 100-meter displacement and a five-minute maximum interval. iOS ultimately decides when background execution is available. Do not force-quit OwnTracks; delayed/offline reports are queued and retain their capture timestamps.

## Privacy and retention

- Privacy-zone coordinates are used only for containment and are never returned after setup.
- Inside a privacy zone, only zone identity and enter/leave/inside time are retained.
- Ordinary raw samples expire after 30 days.
- Samples supporting unresolved suggestions may remain up to 90 days.
- Accepted Places, Visits, and Trips remain until explicitly deleted.
- Raw tracking data uses separate models and serializers and never appears as Passport/map markers.

## Processing and review

TouchGrass normalizes OwnTracks reports, deduplicates them, ignores unusable accuracy, detects stays of roughly 20 minutes within 200 meters, and groups meaningful stays into journey candidates. Location suggestions appear under **Places**. Nothing becomes permanent until accepted.

If tracking appears stale, check the device's Last report value, verify Tailscale is connected on the iPhone, open OwnTracks, and use its manual upload button. A paused or revoked device cannot submit reports; a revoked device must be paired again.
