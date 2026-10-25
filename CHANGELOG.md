# Changelog

## 3.0.0 (unreleased)

### Added
- **Maison Panel shows your Lantern deck.** The bridge publishes the configured buttons and
  accepts presses by button id, so the wall tablet gets multi-step buttons, custom buttons and
  LIVE confirmation, all run by the same engine as phones. Actions run beside the receive
  loop so status updates keep flowing during multi-step buttons.
- **Capability discovery**: the names (never values) of every field and event LIVE Studio
  reports are logged once and listed under Diagnostics.
- **Multi-step buttons**: up to 8 scene, mute and wait steps in one tap (for example BRB + mute
  mic). Steps run in order and stop at the first failure; the button lights up when every
  target is in place. One-tap presets: *BRB and mute mic*, *Back to the game*.
- **LIVE timer** on phones and in the control center.
- **Direct studio buttons on the phone deck.** Scene, microphone and desktop-sound buttons
  talk to LIVE Studio directly and show its real state (current scene lit, Muted / On).
- **Control center** replaces the Tk window: Live control switch, setup checklist, studio
  status, Maison pairing, phone QR and devices, deck editor, settings, activity, diagnostics.
- **Tray icon** with Live control toggle; closing the window no longer stops the deck.
  Single instance: launching again opens the existing control center.
- **Studio test**: switches each deck scene, toggles mic and desktop sound, verifies every
  step and restores the original state. Refused while LIVE.
- **Live updates** pushed to phones and the control center (server-sent events).
- **Persistent named devices**: phones stay paired across restarts; remove one at a time.
- **LIVE guard**: phones confirm scene changes while broadcasting (setting).
- **Remember Live control** after restart (opt-in), **start with Windows** (opt-in).
- **Diagnostics report** and rotating **log file** with token redaction.
- **Update check** against GitHub releases (opt-out; never downloads anything).
- **French** interface on phones and the control center.
- Optional **hotkey backup** for direct buttons when the studio channel is unavailable.
- **Installer** (Inno Setup, per-user), portable ZIP, SHA-256 checksums, signing hook, CI.

### Changed
- Code reorganized into the `lantern/` package with one action engine for every surface.
- LIVE Studio discovery probes every local port of the LIVE Studio process after the known
  ports, and reports what it found.
- Maison replies keep the 2.0 `error` codes and add a specific `reason` and `message`.
- The Maison credential is encrypted with Windows DPAPI; 2.0 files are upgraded on load.
- Folder build (faster start, fewer antivirus false positives) instead of a one-file exe.
- New installs start with the Direct studio deck. Existing `deck.json` files load unchanged
  as keyboard-shortcut buttons.

### Removed
- Tk desktop window and the console `Start-*.cmd` launchers (`python run_lantern.py` instead).

## 2.0.0
Maison Panel direct integration. See git history for 1.x.
