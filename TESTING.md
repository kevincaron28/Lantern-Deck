# Verification

## Standalone Windows launcher — October 15, 2026

Built Windows x64 `Lantern Deck.exe` with Python 3.14.3, PyInstaller 6.22.3 and qrcode 8.2. All seven server unit tests pass. The exact executable was copied into a separate folder whose path contains spaces and run with Python absent from PATH and no PYTHONHOME/PYTHONPATH. It exited successfully after verifying bundled web assets, hidden Tk-window construction, QR rendering, API pairing, live mode changes without re-pairing, configuration persistence and device revocation. No real keys were sent, no existing configuration was loaded or changed, and no browser was opened by the test.

The launcher saves settings outside the binary in `%LOCALAPPDATA%\LanternDeck`. Tests use temporary settings instead. This is a portable unsigned executable; first-run Windows firewall/reputation prompts, a clean Windows installation, physical QR scanning, Samsung Internet and actual TikTok shortcut behavior remain unverified. The smoke test verifies the startup components but does not constitute visual inspection of the native window or testing of the user's default browser launch.

## Samsung phone layout

Verified the paired-device view at 360×800 and 412×915 browser viewports: two columns, four assigned rehearsal controls visible, two unassigned controls hidden, no empty slots and no horizontal overflow. Pairing and rehearsal feedback work. No actual keyboard input was sent. A separate `work/phone-preview.json` was used; the delivered default mappings remain unassigned. Physical Samsung hardware and Samsung Internet remain untested.

## Studio UI redesign

Browser-verified customization save, rehearsal feedback, last-action readout, shortcut-label visibility, focus view, and opening a new key from an empty slot. Desktop and narrow-screen layouts checked for horizontal overflow. JavaScript syntax check passes. Existing mappings and the companion's authentication/execution behavior are unchanged. Screenshots use a separate rehearsal configuration; no actual shortcuts were emitted.

## Original MVP verification

Environment: Windows, Python 3.14.3, Node.js 24.17.0 (used only to check JavaScript syntax; not a runtime requirement).

- Seven automated tests pass: auth/pair/revoke; pairing expiry and rate limits; Host/Origin checks and fixed-file routing; rehearsal and saved-action allowlist; confirmation/cooldown with a mock key sender; atomic persistence and invalid config rejection; shortcut grammar.
- `node --check web/app.js` passes.
- Real browser verification: opened the PC editor, edited a label and shortcut, saved, and tapped the button in rehearsal. The UI displayed “Rehearsed: Rehearsal test”.
- Opened the PC's LAN URL in a second browser tab, entered its pairing code, and verified the tablet view shows the deck without editor privileges. This tests the LAN-address route on the same PC, not a physical Android tablet or firewall traversal.
- Tablet-sized 800×1000 layout inspected visually. At 390×844, the deck uses two columns, buttons measure approximately 160×171 pixels, and document scroll width equals client width (no horizontal overflow).
- Browser tests use `work/preview-deck.json`, separate from the deliverable's default config. No live mappings are shipped.

Not verified: physical Android connectivity, actual Windows key injection into another app, TikTok LIVE Studio 1.14.2 hotkey availability or response, global hotkeys while another app is focused, and privileged-app behavior. No real keyboard shortcuts were emitted by the companion during testing. No streaming settings were changed.

## Version 1.1 — shortcut editor update (October 15, 2026)
Nine server tests pass, including Left Alt normalization, side-specific scan
codes, release order, persistence and mock delivery. Nine JavaScript shortcut
checks pass. A jsdom integration test passes preset preservation/deduplication,
Left Alt recording, Escape cancellation, window-blur cancellation, dropdown
selection and saving. JavaScript syntax checks pass.

The rebuilt executable passed the isolated standalone smoke test with Python
removed from PATH, including the new shortcuts.js asset. No actual keys were
sent. The new editor was DOM-tested, not visually browser-tested; real Windows
key delivery to TikTok and physical Samsung behavior remain unverified.

To reproduce DOM tests: npm install --prefix work/ui-test --no-audit --no-fund jsdom
then node test_editor.js. Other tests: python -m unittest -v and
node test_shortcuts.js. jsdom and Node are development tools only.

## Version 1.2
Added built-in audio-test and full-studio setup, current-shortcut instructions,
profile export, automatic backup before profile replacement, and rehearsal
reset when replacing a profile. Updated editor presets to all six controls.
Server tests (9), recorder checks (9), and editor integration pass. Native
source smoke checks pass for both profiles, export contents, two backups,
rehearsal reset, pairing and assets. See binary smoke report for exact packaged
build verification. Actual TikTok delivery and Samsung hardware remain pending.

## Version 2.0 Maison integration
14 Python tests pass, including typed/sanitized studio state, action allowlist,
stale-state rejection, target mute idempotency and bridge deadline/replay checks.
A local Socket.IO fixture verifies actual wire handshake/subprotocol, join once,
state updates, scene selection, mute target behavior and disconnect invalidation.
This fixture does not run or modify the actual TikTok application.
Maison Panel has 71 passing tests, including owner session/CSRF, one-time pairing,
attempt limits, concurrent code consumption, response correlation, stale revisions,
UI state rendering, one-command-per-tap behavior and existing site regressions.
Native source self-test passes. Packaged executable results accompany the release.
Actual TikTok control and the physical home panel/wife's PC remain unverified
until LIVE Studio is running and the pair-and-offline-test sequence is completed.

### Published verification
The live Maison Deck page returns HTTP 200; unauthenticated state and publisher
requests return HTTP 401. The real PC completed one-time pairing and maintained
an authenticated outbound WebSocket to the production relay with control OFF.
LIVE Studio was not running, so no real scene/mute command was issued.
The 1280x800 browser viewport shows all six 401x160-pixel buttons without
horizontal overflow. Deck is exempt from Maison's automatic idle return home.
The packaged Windows executable passed its standalone smoke checks without
Python on PATH. A physical tablet and wife's PC remain untested.
