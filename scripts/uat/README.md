# TouchGrass UAT environment

This environment is an isolated local copy for black-box beta testing. It uses
ports `8115`/`8116`, its own Docker network and volumes, synthetic photo media,
and mock integration mode. It does not mount the real iCloud folder and it does
not connect to the development containers.

## First setup

Start the normal development database, then run:

```powershell
.\scripts\uat\Setup-Uat.ps1
```

The script temporarily copies the development database, runs the guarded
`prepare_uat` scrub/fixture command, deletes the unsanitized temporary dump, and
captures a sanitized baseline. To skip the development copy and use only
synthetic fixtures:

```powershell
.\scripts\uat\Setup-Uat.ps1 -Fresh
```

Local account passwords are generated once and stored only in
`.uat-artifacts/private/credentials.json`. Neither that file nor the UAT
database baseline is tracked by Git.

## Reset and diagnostics

```powershell
.\scripts\uat\Reset-Uat.ps1
.\scripts\uat\Status-Uat.ps1
```

Reset restores the exact scrubbed baseline without touching the development
database. It also restores the UAT-only media volume and clears the disposable
photo-preview cache. Raw screenshots, logs, network captures, manifests, and
agent reports belong under the current run directory in `.uat-artifacts`.
