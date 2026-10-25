# Verification

## Version 3.0.0 — October 25, 2026

Environment: Windows 10 Pro x64, Python 3.14.3, Node.js 24.17.0, PyInstaller 6.22.3.

### Automated (all passing)
- **57 Python tests** (`python -m unittest discover -s tests -t .`): hotkey grammar and scan
  codes; deck validation, profiles, v2 compatibility, atomic saves and backup pruning;
  settings types; device token hashing, limits and revocation; DPAPI round trip and tamper
  rejection; log redaction; update version comparison; start-with-Windows registry entry
  (fake registry); studio state typing, allowlist error codes, verified idempotent mute,
  rejection, busy lock, port discovery order; engine rehearsal, direct scene/mute with
  targets, LIVE confirmation, offline error and hotkey backup, cooldown, remember-control,
  Maison commands, history; studio test restore and refusal while LIVE/offline; Maison
  relay replies (legacy `error` + `reason`), credential migration, enrollment validation,
  pairing/forgetting, 401 → "pair again"; HTTP host/origin checks, pairing (single use,
  expiry, rate limit, persistence), phone/admin boundaries, phone button filtering, press
  flows, profiles/import backups, device revocation and forget-me, settings validation,
  diagnostics without secrets, studio-test endpoint, loopback-only window request, request
  limits, and the event stream (initial state, pushed change, revocation).
- **Socket.IO wire test** (`tests/test_transport.py`) against `tests/studio-fixture.cjs`:
  discovery skipping a dead port, handshake and subprotocol, single join, mute targets,
  scene switch, full studio test with restore, stream-status change, disconnect detection.
- **Web UI tests** (`npm test`, jsdom): shortcut recorder (9 checks); EN/FR key parity and
  coverage (206 keys); phone deck rendering of real state, mute targets, LIVE confirmation
  round trip, language switch; control center token removal from the URL, pills, checklist,
  Live control switch, scene auto-match, recording and Escape, save payload, profiles,
  settings and device removal.
- **Lint**: `ruff check .` clean (pyflakes, bugbear, bandit subset, naming, pyupgrade).

### Packaged executable
`build.ps1` built `outputs/dist/Lantern Deck/` (33 MB) and
`Lantern-Deck-3.0.0-Portable.zip` (17 MB). The copied folder in a path with spaces, with
Python removed from PATH, passed its `--self-test`: bundled assets, phone pairing, rehearsal
and Live control, event stream, control-center state and QR, profiles/backup/export,
persistent devices and revocation, DPAPI, tray backend. No real keys were sent.

The built exe was also launched for real in tray mode on a spare port and data folder:
the server answered, unauthenticated API calls returned 401, a second launch handed off to
the running instance (which opened its Edge app window) and exited, and the log recorded
both starts.

The installer was **not** built on the development PC (Inno Setup is not installed there);
CI installs Inno Setup and builds it. The build is unsigned (no certificate configured).

### Browser check
The control center and phone deck were run against the fake studio
(`tools/dev_server.py`) and inspected at desktop and 375×812 phone sizes: live studio pills,
checklist progression, scene auto-match and save, pairing a phone, current-scene highlight,
mute state, Live control ON, scene switch and mic mute from the phone, studio test with
restore, French interface.

### Not yet verified (needs the real setup)
- **Real LIVE Studio.** LIVE Studio was not running during development, so no real scene
  or mute command has been sent by any version. Do this before relying on it:
  open LIVE Studio (not live), start Lantern Deck, and click **Run studio test**. The
  result, the port used and the LIVE Studio version are saved in
  `%LOCALAPPDATA%\LanternDeck\studio-test-latest.json` and shown under Diagnostics.
- **`stream_status` meaning.** Values other than 0 are treated as LIVE. Confirm by starting a
  private/test broadcast and checking the LIVE pill.
- Physical Samsung phone / Samsung Internet, Windows firewall prompt on a clean PC, the
  Maison relay with 3.0 (protocol unchanged; replies gained `reason`/`message`), the
  installer, start with Windows after a reboot, and SmartScreen behaviour.

## Earlier versions
Version 2.0 added the Maison integration (14 Python tests, fixture wire test, packaged
self-test; real LIVE Studio control unverified). Versions 1.0–1.2 covered the keyboard
shortcut deck. See git history for their full notes.
