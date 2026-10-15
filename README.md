# Lantern Deck

A free Windows companion for Maison Panel's six-button TikTok LIVE Studio deck, with an optional local shortcut deck for Samsung Android phones. Independent software; no affiliation with TikTok or Elgato.

## Download and set up version 2.0

Download **Lantern-Deck-2.0-Maison.zip** from this repository's Releases page, extract it, and run **Lantern Deck.exe**. No Python installation is needed.

Follow [MAISON-SETUP.txt](MAISON-SETUP.txt) to pair your PC with the Maison Deck tab and select your four scenes. Microphone and desktop-sound controls need no hotkey assignments in Maison mode. Maison requires its existing owner account, Internet access, and the companion running on the streaming PC. The matching panel code is in [Maison Panel](https://github.com/kevincaron28/Maison-Panel/tree/codex/panel-audit).

Automated tests and packaged-app checks passed. Actual scene switching and audio control against a running LIVE Studio installation remain unverified. The direct integration uses an internal, version-sensitive protocol; test offline before a broadcast. This is an unsigned Windows x64 build.

The sections below describe the optional local phone/shortcut mode, which can run without an account or cloud service. Open that mode in the companion to use the phone editor.

## Optional phone shortcut setup

1. Open **Lantern Deck.exe** on your Windows PC and expand **Phone shortcut mode (optional)** to open the PC editor. No Python installation or terminal required.
2. Select **Customize deck** and enter the shortcuts you configured in LIVE Studio.
3. On your Samsung phone, scan the QR code in the Lantern Deck window, open the link and enter its pairing code. Both devices must be on the same private network.
4. Test in rehearsal, then check **Enable keyboard control** in the PC window. Switching modes does not require a restart or another pairing.

Keep the app window open. Closing it stops control. The app starts in rehearsal on each launch, and phones must pair again after a restart. If Windows requests network access, allow only your trusted **Private** network. This Windows x64 executable is unsigned and may receive a Windows reputation warning; it does not change security settings or require administrator access.

Your settings live in `%LOCALAPPDATA%\LanternDeck\deck.json`, outside the executable. Use **Import existing deck** for a configuration saved by the earlier version. Existing settings are backed up before import replaces them. When updating the executable, close the app first; your settings remain in the data folder. To remove the app, close it and delete the executable; remove the data folder separately only if you also want to erase your saved layout.

If several addresses appear above the QR code, choose your home-network adapter. If none appear, connect the PC to Wi-Fi/Ethernet and restart. The QR contains only the local device URL, never the admin token. No internet access is needed while using the app.

See **QUICK-START.txt** for the short setup guide. The standalone build bundles Python, Tk and QR-code support. The source server itself still uses only the Python standard library.

## Advanced: run the Python source

The console instructions below are an alternative for developers. They are not needed for the standalone app.

1. Install Python 3.10 or newer from [python.org](https://www.python.org/downloads/windows/) if needed. Enable the installer option that adds Python to PATH. Python 3.14.3 was already available on the development PC.
2. Extract this whole folder somewhere writable. Keep `server.py` and the `web` folder together.
3. Double-click **Start-Rehearsal.cmd**. Keep its console window open. Rehearsal mode never sends keyboard input.
4. Copy the complete **PC editor** URL printed in that window into a browser on this PC. This URL contains a temporary admin token; keep it private. If an already-open deck only changes its address without showing the editor, reload it.
5. Click **Customize deck**. Set labels, text/emoji icons, accent colors and shortcut mappings. Add or remove buttons (1–32), then choose **Save changes**. Blank shortcuts intentionally disable buttons. All starter buttons are unassigned; their names are ideas, not preconfigured TikTok functions.

The phone interface shows only buttons with assigned shortcuts, in two large columns in portrait. There are no empty slots. Labels and icons are enlarged, and shortcut codes and desktop toolbars are hidden. When nothing is assigned, the phone explains how to configure controls on the PC. The PC editor still shows all buttons so you can assign or remove them. The last-action readout records delivery/rehearsal feedback for this browser session, not TikTok application state. The six original icon tokens (`01`, `02`, `03`, `♫`, `▧`, `✦`) render as crisp built-in line icons; other text and emoji remain customizable.

For a Samsung Android phone, open the printed device URL in your browser and pair using the PC's code. Keep the phone upright for the two-column layout. Start with just your essential shortcuts; leave other mappings blank to keep them off the phone. The layout has been browser-tested at 360 and 412 CSS pixels wide, but has not been tested on physical Samsung hardware or Samsung Internet. Use an up-to-date browser.

Accepted shortcuts: one or more of `Ctrl`, `Alt`, `Shift`, followed by a letter, digit, F1–F24, Space, Enter, Tab, Esc or an arrow name. Example: `Ctrl+Shift+1`. Windows-key shortcuts, shell commands, scripts and arbitrary text typing are not supported. Use combinations that do not conflict with Windows or other apps.

## Connect the Android tablet

1. Connect the tablet and PC to the same trusted home/private network. The PC can use Ethernet while the tablet uses Wi-Fi.
2. Open Chrome on the tablet and type one of the **Tablet** URLs printed by the companion, including `http://` and `:8765`. Do not use `localhost` on the tablet; that points at the tablet itself.
3. Enter the eight-digit code from the PC console or PC editor. Codes expire after five minutes and can be used once. Click **New code** in the PC editor for another device.
4. Tap a configured button. You should see **Rehearsed: …**. Try **Full screen** for a larger control surface. You can bookmark the URL or add a browser shortcut to your home screen; this is a website, not an installable offline PWA.
5. Keep the tablet awake using its display timeout setting as needed. Automatic wake lock is not included.

If Windows asks about Python network access, allow it only for your trusted **Private** network. If needed, use Windows Defender Firewall's advanced settings to allow inbound TCP port 8765 on the Private profile, with remote addresses restricted to Local subnet. Do not disable the firewall or allow Public networks. No firewall rules are created automatically.

## Enable keyboard output with the console version

1. Finish rehearsal, then stop its console with Ctrl+C (or close the window).
2. Double-click **Start-Keyboard.cmd**. The new console must say **KEY OUTPUT ENABLED**. Reopen the newly printed PC editor URL and re-pair the tablet; all credentials reset on restart. Saved button mappings remain in `deck.json`.
3. First validate a harmless shortcut in a disposable document, away from any live broadcast. For example, temporarily map `Ctrl+A`, focus a scratch Notepad document, and tap the tablet button to select its text. Remove or replace that mapping afterward.
4. Test each intended LIVE Studio shortcut while offline before relying on it during a broadcast. Use **Ask before sending** for consequential actions. No start/stop-stream button is included by default.

The bridge uses Windows `SendInput`, which sends input into the current interactive desktop. It does not target or focus TikTok. A foreground app may receive the shortcut unless the intended app registers it globally. Focus, privilege levels, app settings and other software affect behavior. Running both apps as a normal user is preferred. The server rejects output while relevant keys/modifiers are physically held to avoid stuck or mixed shortcuts. It releases its keys after each chord and attempts cleanup if Windows accepts only part of a batch.

**“Keys sent” means Windows accepted keyboard events; it does not confirm the application acted.** Buttons have no latched on/off state and do not claim to know microphone, camera, scene or livestream status. Confirm those states inside LIVE Studio. A failed/ambiguous request is never retried automatically, because retrying could toggle an action twice.

## TikTok LIVE Studio compatibility

Research checked October 11, 2026 against TikTok's [official hotkey guide](https://www.tiktok.com/live/studio/help/article/Best-practice/Use-hotkeys-to-make-frequent-actions-snappier). TikTok documents user-configured hotkeys and says there are no default hotkeys. This MVP uses keyboard shortcuts rather than an assumed public automation API or application-state integration.

The development PC's Windows uninstall registry reports **TikTok LIVE Studio 1.14.2**. That is installed-package metadata, not proof of available functions or working hotkeys. Its in-app hotkey settings were not inspected or modified, and keyboard compatibility with that version has not been verified.

Before using this with your installation, open its hotkey settings and check which actions are actually offered. Configure your chosen combinations there yourself, then enter the exact same combinations in Lantern Deck. If an action is absent or does not respond to a physical keyboard, this deck cannot add support for it. Do not assume an online guide's action list applies to every release/account. No actual livestream was started or stopped in development.

## Pairing and network boundaries

- The PC editor requires a randomly generated 256-bit token **and** a loopback connection. Tablets cannot change mappings, generate codes or revoke devices.
- Pairing codes have eight digits, a five-minute lifetime, one-time use and a global limit of ten attempts/minute. At most 16 paired device tokens are held per server run.
- Tablet tokens are random, held in browser session storage and accepted until revoked or the companion restarts. Closing the browser tab normally clears its local token. **Disconnect** forgets the browser's copy; **Revoke all tablets** invalidates every tablet token at the server.
- Only saved button IDs can execute. A request cannot supply a replacement shortcut or a shell command. Shortcut execution is serialized and limited to one action per 350 milliseconds.
- The server checks Host and Origin, serves only three fixed web files, uses no external scripts/fonts, and does not log tokens or request bodies.
- **This MVP uses unencrypted HTTP. Use only a trusted private LAN.** Pairing does not protect against a hostile Wi-Fi participant intercepting traffic. Do not expose the port to the internet, configure port forwarding, or put it behind a public tunnel. HTTPS and per-device named management are future improvements.
- Anyone with a paired tablet can trigger its configured shortcuts. Stop the companion to disable access immediately. The listener binds all IPv4 interfaces by default; a narrower interface can be selected with `--bind`.

## Troubleshooting and command line

From this folder:

```powershell
python server.py                         # rehearsal, port 8765
python server.py --enable-keys           # real keyboard output
python server.py --port 8877             # alternate port
python server.py --bind 127.0.0.1        # PC-only rehearsal
python -m unittest -v                    # tests; no real keys sent
```

- **Python not found:** install Python and enable PATH, then reopen the launcher. If `py` works but `python` does not, run `py server.py` from this folder.
- **Address already in use:** stop the earlier companion or choose another port; include that port in the tablet URL and firewall rule.
- **PC unavailable / cannot load:** check the companion is running, both devices share a network, and the correct Private firewall rule exists. Guest Wi-Fi/client isolation and some VPNs prevent device-to-device connections. If your IP changed, restart the companion and use the new printed URL.
- **Several tablet addresses:** choose your home-network adapter's IPv4 address (check `ipconfig`); virtual adapters can also be listed.
- **Code expired:** generate a new code from the PC editor. The console's original code is not refreshed after pairing.
- **Keys sent but nothing happens:** verify the mapping with a physical keyboard, the target app's focus/global-hotkey behavior, and matching privilege levels. This software cannot verify app state.
- **Configuration will not save:** the folder must be writable. `deck.json` is written atomically. Back it up to preserve your layout; to reset, stop the companion and rename it. Never hand-edit it while the server is running.
- **Deck shows offline after restart:** credentials are deliberately invalidated; open the new editor URL and pair again.

## Project structure and testing

`server.py` provides HTTP, authentication, validation, configuration persistence and the Windows keyboard bridge. `web/` is the responsive UI. `test_server.py` covers API/security behavior with temporary files and a mock key sender. See `TESTING.md` for what was actually verified and what still requires hardware/application testing.

This is an achievable LAN MVP, not a hardened internet service. The desktop executable is portable, with no system installer, autostart, cloud component or telemetry.

## Build the Windows executable

Run `build.ps1` from PowerShell with Python installed. It creates a separate environment under `work/`, installs the pinned build dependencies, and packages `launcher.py`, the web assets and the runtime into `outputs/Lantern Deck.exe` using PyInstaller. The build is Windows-specific. Run the packaged smoke test with `"Lantern Deck.exe" --self-test <report-path>` from a process runner that waits for completion; it writes a JSON report and never sends keys or opens the browser. This is a development test, not part of normal setup.

For development checks, install the Python dependencies from `requirements-build.txt` and run `python -m unittest test_server test_studio`. Install Node test dependencies with `npm ci`, then run `npm test`. On Windows, `python test_transport.py` exercises a local Socket.IO fixture without controlling LIVE Studio. After building, `python tests/smoke_bundle.py` checks the standalone executable with Python removed from its environment. Third-party distribution notices are in `licenses/` and must accompany the executable.

## Version 1.1 shortcut editor
Ready-made Microphone, Main scene, Close-up and Be right back controls fill
unassigned matching buttons while preserving configured shortcuts. Assign the
same suggested shortcuts in LIVE Studio once. PC recording captures left/right
modifiers; dropdowns offer a keyboard-free alternative. Left Alt alone and
Left Alt plus a supported key are accepted. Windows output uses physical
modifier scan codes, including extended right Alt/right Ctrl.

Upgrade by closing the old app, extracting the new ZIP and launching its EXE.
Saved buttons remain in the existing LocalAppData folder. Re-pair your phone.

## Maison direct integration — version 2.0
Maison mode is now the primary launcher view; the existing phone/hotkey controls
are optional. Pair from Maison's Deck page and select real scenes there. See
MAISON-SETUP.txt. No scene/media/TikTok-account files are copied. The companion
uses LIVE Studio's local, version-sensitive controller channel, not Elgato's
plugin runtime. It exposes only scenes and the two audio controls.

The public hosted panel requires its existing owner session. A dedicated relay
uses one-time enrollment, hashed publisher credentials, TLS and short-lived,
non-retried commands. Runtime studio status is not written to durable storage.
The local credential is maison-connection.json beside deck.json and must never
be committed or included in exports. The application starts direct control OFF.

The software is independently implemented and free of license fees; Cloudflare
account limits and Internet availability still apply. This is not an official
TikTok product. The old standard-library-only claim applies to the shortcut
server, not the new companion (websocket-client and psutil are bundled).
