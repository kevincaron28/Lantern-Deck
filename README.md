# Lantern Deck

A private control deck for **TikTok LIVE Studio** on Windows. Switch scenes and mute the
microphone or desktop sound from a phone, a tablet or your Maison home panel, and see
LIVE Studio's real state on every button.

Independent software: not affiliated with TikTok or Elgato. MIT licensed, no account,
no subscription, no telemetry.

## What it does

- **Direct studio control.** Lantern Deck talks to LIVE Studio's local controller
  channel. Scene buttons light up on the current scene; mute buttons show *Muted* or *On*.
  No hotkeys needed.
- **Phone and tablet deck.** Scan a QR code, enter a one-time code, done. Paired devices
  stay paired across restarts until you remove them.
- **Maison Panel.** Optionally control the PC from the Deck tab of your Maison home panel.
- **Safe by default.** Starts in rehearsal (nothing reaches LIVE Studio) until you turn
  on **Live control**. While you are LIVE, phones confirm scene changes. Every action is
  verified against LIVE Studio's state; nothing is ever retried automatically, so a toggle
  can never flip twice.
- **Multi-step buttons.** One tap for several steps, such as switching to BRB and muting
  the mic. Steps run in order and stop at the first failure. A LIVE timer shows how long
  you have been broadcasting.
- **Keyboard shortcuts** remain available for anything else, and as an optional backup
  when LIVE Studio's controller is not reachable.
- **Runs in the tray.** Closing the control center keeps the deck running. Optional
  start with Windows. English and French.

## Install

Download from the [Releases page](https://github.com/kevincaron28/Lantern-Deck/releases):

- `Lantern-Deck-<version>-Setup.exe`: installs for your Windows user (no administrator
  rights) with a Start menu entry and an uninstaller.
- `Lantern-Deck-<version>-Portable.zip`: extract anywhere and run `Lantern Deck.exe`.

Check downloads against `SHA256SUMS-<version>.txt`. Builds are unsigned unless a release
says otherwise, so Windows SmartScreen may warn the first time.

## First run (5 minutes)

1. Open LIVE Studio on its main studio screen, then start Lantern Deck. The **control
   center** opens and the tray icon appears.
2. Follow the **setup checklist**:
   1. *LIVE Studio detected*: turns green when the controller channel connects.
   2. *Connect a control surface*: scan the phone QR code and enter the pairing code,
      and/or pair Maison (see [MAISON-SETUP.txt](MAISON-SETUP.txt)).
   3. *Assign your scenes*: **Edit buttons → Match scenes by name**, check, save.
   4. *Test while offline*: **Run studio test** switches through your scenes, toggles mic
      and desktop sound, verifies each step and restores everything. Refused while LIVE.
   5. *Go live*: flip **Live control** on.

Phone and PC must be on the same private network. If Windows asks about network access,
allow **Private** networks only. See [QUICK-START.txt](QUICK-START.txt) for the short version.

## Security model

- Phones get a random device token through a one-time 8-digit code (5-minute lifetime,
  10 attempts/minute, single use, at most 16 devices). Only SHA-256 hashes of tokens are
  stored. Phones can press buttons; they cannot change the deck or settings.
- The control center needs a per-launch admin token **and** a loopback connection.
- Requests can only name a saved button. Studio commands are limited to scene, microphone
  and desktop-sound; there is no start/stop broadcast, shell, or arbitrary key input.
- Host and Origin headers are checked; a strict Content-Security-Policy is sent; tokens
  are never logged (the log redacts token-like strings).
- The Maison credential is encrypted with Windows DPAPI (readable only by your Windows
  account). Version 2.0 plaintext credentials are upgraded automatically.
- **The phone link is plain HTTP.** Use only a trusted home network. Never port-forward
  port 8765 or expose it to the internet.

## Where things are stored

`%LOCALAPPDATA%\LanternDeck\`: `deck.json` (buttons), `settings.json`, `devices.json`
(token hashes), `maison-connection.json` (DPAPI-encrypted), `deck-backup-*.json` (last 10),
`studio-test-latest.json` and `logs\lantern.log`. Uninstalling keeps this folder.

## Compatibility notes

The LIVE Studio controller channel is internal and version-sensitive. Lantern Deck tries
known controller ports first, then probes any other port the LIVE Studio process listens
on locally, and reports exactly what it found under **Diagnostics**. If an update breaks
the channel, the deck says so rather than guessing. Use the studio test after LIVE Studio
updates. `stream_status` values other than 0 are treated as "LIVE" (verify with your
version; see [TESTING.md](TESTING.md)).

## Develop

Requires Python 3.12+ (3.14 used) and Node.js 24 for UI tests.

```powershell
python -m venv work/build-env
work/build-env/Scripts/python.exe -m pip install -r requirements-dev.txt
npm ci

work/build-env/Scripts/python.exe -m ruff check .                         # lint
work/build-env/Scripts/python.exe -m unittest discover -s tests -t .      # Python tests
npm test                                                                  # web UI tests (jsdom)
work/build-env/Scripts/python.exe tools/dev_server.py                     # UI against a fake LIVE Studio
work/build-env/Scripts/python.exe run_lantern.py                          # the real app from source
./build.ps1                                                               # exe, self-test, ZIP, installer
```

`tools/dev_server.py` runs the app on port 8790 against `tests/studio-fixture.cjs`, a fake
LIVE Studio (type `live` / `offline` to change its broadcast state). It never sends keys and
never contacts Maison.

### Layout

| Path | Purpose |
|---|---|
| `lantern/studio.py` | LIVE Studio controller adapter: discovery, verified commands, error codes |
| `lantern/engine.py` | One action engine for phones, the control center and Maison; studio test |
| `lantern/server.py` | Local HTTP API, pairing, live event stream (SSE over fetch) |
| `lantern/bridge.py` | Maison Panel relay client and DPAPI credential storage |
| `lantern/desktop.py` | Tray icon, single instance, Edge app window, start with Windows |
| `lantern/deck.py`, `settings.py`, `devices.py` | Saved deck, preferences, paired devices |
| `web/` | Phone deck (`index.html`), control center (`control.html`), EN/FR strings |
| `tests/` | Python tests, jsdom UI tests, fake studio, packaged-app smoke test |
| `installer/` | Inno Setup script |

### Releases

Bump `VERSION` in `lantern/__init__.py` and `package.json` (a test keeps them equal), update
`CHANGELOG.md`, then tag `vX.Y.Z`. CI lints, tests, builds, self-tests the packaged exe and
attaches the ZIP, installer and checksums to a draft GitHub release.

Code signing: set `LANTERN_SIGN_THUMBPRINT` (certificate in your store) or
`LANTERN_SIGNTOOL_ARGS` (for example Azure Trusted Signing) before running `build.ps1`.

Third-party notices are in `licenses/` and ship with every build. pystray is LGPL-3.0.
