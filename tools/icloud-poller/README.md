# TouchGrass iCloud Photos poller

This Windows-user-session helper indexes the configured iCloud Photos folder without copying originals. It never edits, moves, pins, unpins, or deletes iCloud files.

1. Extract the Windows ExifTool executable anywhere under Downloads (or install it on PATH).
2. In TouchGrass, open Settings → Integrations → iCloud Photos and pair the Windows poller.
3. Run the one-time `setup` command shown by TouchGrass.

`setup` automatically locates and validates ExifTool, encrypts the credential with DPAPI, verifies the first server report, installs the signed-in-user Task Scheduler entry, and starts it. No separate configure, scan, or install commands are required.

The Task Scheduler entry runs at sign-in because iCloud for Windows and DPAPI credentials belong to the signed-in Windows user. Local state is stored under `%LOCALAPPDATA%\TouchGrass\iCloudPoller`.
