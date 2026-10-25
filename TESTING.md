# Verification

## Version 3.0.0 — October 25, 2026

Environment: Windows 10 Pro x64, Python 3.14.3, Node.js 24.17.0, PyInstaller 6.22.3.

### Automated (all passing)
- **62 Python tests** (`python -m unittest discover -s tests -t .`): hotkey grammar and scan
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
- Multi-step buttons: validation limits (1–8 steps, waits 100–5000 ms, 10 s total, at least
  one real step, no hotkey steps), rehearsal, in-order execution, stop at first failure,
  LIVE confirmation when a step changes scenes, offline refusal; LIVE timer start/stop.
- **Socket.IO wire test** (`tests/test_transport.py`) against `tests/studio-fixture.cjs`:
  discovery skipping a dead port, handshake and subprotocol, single join, mute targets,
  scene switch, full studio test with restore, stream-status change, disconnect detection.
- **Web UI tests** (`npm test`, jsdom): shortcut recorder (9 checks); EN/FR key parity and
  coverage (223 keys); phone deck rendering of real state, mute targets, LIVE confirmation
  round trip, multi-step key state, LIVE timer text, language switch; control center token removal from the URL, pills, checklist,
  Live control switch, scene auto-match, recording and Escape, save payload, profiles,
  settings and device removal, multi-step presets and step editing.
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

### Streaming PC (reported October 25, 2026)
On the streaming PC (TikTok LIVE Studio **1.38.0**), commit 4b49b6c was built with
`build.ps1 -SkipInstaller`; the packaged self-test passed. The running app logged
"LIVE Studio controller connected on port 28189": the real controller handshake works on 1.38.0,
where 28189 is the only port LIVE Studio listens on (IPv6 any). The 2.0 Maison credential was
upgraded to DPAPI and the Maison relay connected. Not yet done there: studio test, tablet
pairing, firewall prompt. That LIVE Studio account must never broadcast, so `stream_status`
was checked from the log instead: commit 92718b1 logged "LIVE Studio installed: 1.38.0" and
"Studio state: 5 scenes, stream_status=0" while idle, with no "Broadcast detected as LIVE" line
in either run. **0 = not live is confirmed on 1.38.0**; which non-zero value means live is still
unobserved (it only adds a confirmation before scene changes).

**Real control confirmed (06:29–06:31).** The in-app studio test passed on LIVE Studio 1.38.0
(scenes Start / Main / BRB / END, mic and desktop sound toggled and restored). With Live control
ON, the Maison wall tablet then switched scenes and muted/unmuted the mic and desktop sound; every
command was confirmed by LIVE Studio's state. Polarity checked by eye in LIVE Studio:
`mic_mute` / `audio_mute` = `True` means muted for both. The tablet's flashing and unclear mute
display are Maison Panel UI issues (its `js/deck.js`), not Lantern Deck.

### Not yet verified (needs the real setup)
- **Which non-zero `stream_status` means LIVE** (0 = not live is confirmed on 1.38.0). Non-zero
  values are treated as LIVE; only observable during a real broadcast.
- Physical Samsung phone / Samsung Internet on the local phone deck, Windows firewall prompt on
  a clean PC, the installer, start with Windows after a reboot, and SmartScreen behaviour.
  (The Maison relay with 3.0 is verified on the streaming PC.)

### Closing the last unknowns (owner checklist)
1. **Which `stream_status` means LIVE.** Never on the family account. With LIVE Studio signed in
   to a *different*, throwaway TikTok account, start a short private broadcast, then stop it.
   `%LOCALAPPDATA%\LanternDeck\logs\lantern.log` records every change as
   `Studio state: … stream_status=N`, and the Diagnostics report lists all reported field names.
   Expected: non-zero while live, 0 again after. Send the log lines to update `is_live`.
2. **Physical phone.** On a Samsung phone on the home Wi-Fi, scan the control-center QR, pair,
   tap a scene and the mic with Live control ON, and check the tiles follow LIVE Studio.
   Allow Windows Firewall on *Private* networks only if the phone cannot load the page.
3. **Reboot test.** With Start with Windows and Remember Live control enabled, restart the
   streaming PC, open LIVE Studio, and press a tablet button without touching the PC.

## Earlier versions
Version 2.0 added the Maison integration (14 Python tests, fixture wire test, packaged
self-test; real LIVE Studio control unverified). Versions 1.0–1.2 covered the keyboard
shortcut deck. See git history for their full notes.
