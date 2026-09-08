# iCloud Photos poller

TouchGrass can index metadata from iCloud for Windows without copying original
photos into AdventureLog media storage. The Windows poller reads
`C:\Users\spenc\iCloudPhotos\Photos`, stores its checkpoint locally, and sends
small authenticated JSON batches to TouchGrass.

## Before you start

1. Install iCloud for Windows and allow Photos to synchronize.
2. Extract the Windows [ExifTool](https://exiftool.org/) executable under
   Downloads or install it on PATH. TouchGrass discovers and validates it.
3. Set `ICLOUD_PHOTOS_ROOT` in `.env` if the library is somewhere other than the
   default path, then recreate the backend container.
4. Open **Settings → Integrations → iCloud Photos**, assign the source to
   Spencer, and select **Pair poller**.

TouchGrass displays one setup command because a browser cannot install a local
Windows background process by itself. It discovers ExifTool, verifies
connectivity, replaces the displayed one-time token with a new Windows
DPAPI-encrypted credential, installs automatic startup, and starts scanning.
Apple credentials are never requested or stored. All later controls operate from
TouchGrass Settings without another command.

## Test and install

Run the generated setup command from the repository. For later diagnostics use:

```powershell
py tools\icloud-poller\icloud_poller.py scan-now
py tools\icloud-poller\icloud_poller.py status
```

The poller runs in the signed-in user session. It first attempts a limited
`ONLOGON` scheduled task. On Windows installations that deny non-administrator
task creation, it automatically uses the current user's Startup folder instead;
no administrator terminal is required. Other available commands are `run`,
`pause`, `resume`, `retry-errors`, and `uninstall`.

## Cloud-only media

The historical pass is newest-first and uses a single metadata worker. Reading a
cloud-only placeholder may cause iCloud for Windows to download it. TouchGrass
does not pin, unpin, edit, move, rename, or delete the file and does not
automatically dehydrate it afterward. Before each metadata batch, the poller
checks the photo library's drive and stops hydration when less than 10 GB remains.
It keeps reconciling already-visible metadata and resumes processing only when
capacity is available. See Apple's documentation for
[download status](https://support.apple.com/guide/icloud-windows/view-download-and-sharing-status-icwacec33fdd/1.0/icloud/1.0)
and [iCloud Photos behavior on Windows](https://support.apple.com/en-au/guide/icloud-windows/icw2ed20ffd1/icloud).

Originals are served from the read-only `/icloud-photos` bind mount. HEIC
previews and video poster frames are disposable, metadata-stripped derivatives
stored in the separate preview cache. Removing the cache does not affect the
iCloud library or indexed metadata.

## Troubleshooting

- **Waiting for first report:** run `scan-now` in the same Windows account used
  during setup.
- **Photo folder unavailable:** check `ICLOUD_PHOTOS_ROOT`, Docker Desktop file
  sharing, and the backend container mount.
- **Metadata errors:** verify the configured ExifTool executable, then use
  `retry-errors`.
- **Original unavailable:** open iCloud for Windows and allow the placeholder to
  finish downloading; the next reconciliation restores availability.
- **Changed TouchGrass address:** revoke and pair the source again so the poller
  receives the current backend ingestion endpoint.
