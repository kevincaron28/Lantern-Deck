"""Desktop launcher and frozen-app smoke test for Lantern Deck."""
import argparse
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import urllib.request
import webbrowser

import qrcode
from server import Handler, State, ThreadingHTTPServer, validate, studio_profile
from maison_bridge import MaisonBridge, enroll, ORIGIN
import queue


def addresses():
    """Enumerate local adapter addresses without contacting an internet service."""
    found = set()
    try:
        found.update(socket.gethostbyname_ex(socket.gethostname())[2])
    except OSError:
        pass
    return sorted(ip for ip in found if not ip.startswith('127.') and ip != '0.0.0.0')


def start_server(path, host='0.0.0.0', port=8765):
    state = State(path)  # Always starts in rehearsal, even after an earlier enabled session.
    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    server.state = state
    ips = addresses()
    server.allowed_hosts = {f'{ip}:{server.server_port}' for ip in ['localhost', '127.0.0.1', *ips]}
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, ips


def save_config(state, config):
    config = validate(config)
    with state.lock:
        temp = state.path.with_suffix('.tmp')
        temp.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding='utf-8')
        temp.replace(state.path)
        state.config = config


class Companion:
    def __init__(self, root, server, ips, open_browser=True):
        self.root, self.server, self.state = root, server, server.state
        self.bridge = None
        self.bridge_messages = queue.Queue()
        self.pairing_bridge = False
        self.bridge_path = self.state.path.with_name('maison-connection.json')
        self.admin_url = f'http://localhost:{server.server_port}/#admin={self.state.admin}'
        root.title('Lantern Deck 2.0 · Maison')
        root.configure(bg='#10151e')
        root.geometry('620x610')
        root.minsize(540, 540)
        root.protocol('WM_DELETE_WINDOW', self.close)
        style = ttk.Style(root)
        style.theme_use('clam')
        style.configure('TFrame', background='#10151e')
        style.configure('TLabel', background='#10151e', foreground='#dbe7ef', font=('Segoe UI', 11))
        style.configure('TButton', font=('Segoe UI', 11), padding=9)
        style.configure('TCheckbutton', background='#10151e', foreground='#dbe7ef', font=('Segoe UI', 12), padding=10)
        style.map('TCheckbutton', background=[('active', '#203040')])
        shell = ttk.Frame(root)
        shell.pack(fill='both', expand=True)
        scroll = tk.Canvas(shell, background='#10151e', highlightthickness=0)
        bar = ttk.Scrollbar(shell, orient='vertical', command=scroll.yview)
        bar.pack(side='right', fill='y')
        scroll.pack(side='left', fill='both', expand=True)
        scroll.configure(yscrollcommand=bar.set)
        frame = ttk.Frame(scroll, padding=24)
        content = scroll.create_window((0, 0), window=frame, anchor='nw')
        scroll.bind('<Configure>', lambda event: scroll.itemconfigure(content, width=event.width))
        frame.bind('<Configure>', lambda _: scroll.configure(scrollregion=scroll.bbox('all')))
        root.bind('<MouseWheel>', lambda event: scroll.yview_scroll(-int(event.delta/120), 'units'))
        ttk.Label(frame, text='LANTERN DECK', font=('Segoe UI', 21, 'bold'), foreground='#64e2d2').pack(anchor='w')
        ttk.Label(frame, text='Your Maison panel. Your studio controls.').pack(anchor='w', pady=(4, 18))
        ttk.Label(frame, text='MAISON PANEL · DIRECT STUDIO CONTROL', font=('Segoe UI', 12, 'bold')).pack(anchor='w')
        ttk.Label(frame, text='On the home panel: Deck > Connect a PC. Enter its code here.', wraplength=530).pack(anchor='w', pady=(5, 8))
        connect = ttk.Frame(frame); connect.pack(fill='x')
        self.maison_code = tk.StringVar()
        ttk.Entry(connect, textvariable=self.maison_code, width=12, font=('Consolas', 17)).pack(side='left')
        self.maison_pair_button = ttk.Button(connect, text='Connect to Maison', command=self.pair_maison)
        self.maison_pair_button.pack(side='right')
        self.direct_enabled = tk.BooleanVar(value=False)
        ttk.Checkbutton(frame, text='Allow Maison to control scenes and audio', variable=self.direct_enabled, command=self.set_direct_mode).pack(anchor='w')
        self.maison_status = tk.StringVar(value='Not connected. No hotkeys needed for Maison mode.')
        ttk.Label(frame, textvariable=self.maison_status, wraplength=530).pack(anchor='w', pady=(4, 18))
        ttk.Button(frame, text='Open Maison Deck', command=lambda: webbrowser.open(ORIGIN+'/deck.html')).pack(fill='x', pady=(0, 12))
        ttk.Label(frame, text='Keep this app and LIVE Studio open. On the panel, choose your scenes in Configuration. No hotkeys are needed.', wraplength=530).pack(anchor='w', pady=(0, 12))
        legacy = ttk.Frame(frame)
        def toggle_legacy():
            if legacy.winfo_manager():
                legacy.pack_forget()
            else:
                legacy.pack(fill='x', pady=(12, 0))
        ttk.Button(frame, text='Phone shortcut mode (optional)', command=toggle_legacy).pack(fill='x')
        frame = legacy
        profiles = ttk.Frame(frame)
        profiles.pack(fill='x', pady=(0, 8))
        ttk.Button(profiles, text='Audio test: 2 buttons', command=lambda: self.use_profile(True)).pack(side='left')
        ttk.Button(profiles, text='Full studio: 6 buttons', command=lambda: self.use_profile(False)).pack(side='right')
        ttk.Button(frame, text='Show matching TikTok shortcuts', command=self.show_setup).pack(fill='x', pady=(0, 8))
        ttk.Button(frame, text='1. Open PC controls', command=self.open_editor).pack(fill='x')
        ttk.Label(frame, text='Choose your buttons and assign their shortcuts on the PC.', wraplength=530).pack(anchor='w', pady=(7, 16))
        ttk.Label(frame, text='2. Scan with your phone camera', font=('Segoe UI', 13, 'bold')).pack(anchor='w')
        ttk.Label(frame, text='Phone and PC must be on the same private network.').pack(anchor='w', pady=(5, 8))
        self.url = tk.StringVar(value=f'http://{ips[0]}:{server.server_port}/' if ips else '')
        urls = [f'http://{ip}:{server.server_port}/' for ip in ips]
        self.selector = ttk.Combobox(frame, textvariable=self.url, values=urls, state='readonly', font=('Segoe UI', 12))
        self.selector.pack(fill='x')
        self.selector.bind('<<ComboboxSelected>>', lambda _: self.draw_qr())
        self.canvas = tk.Canvas(frame, width=216, height=216, bg='white', highlightthickness=0)
        self.canvas.pack(pady=12)
        self.draw_qr()
        ttk.Label(frame, text='Then enter this pairing code on your phone:').pack()
        self.code = tk.StringVar()
        ttk.Label(frame, textvariable=self.code, font=('Consolas', 25, 'bold'), foreground='#64e2d2').pack(pady=4)
        self.pair_status = tk.StringVar()
        ttk.Label(frame, textvariable=self.pair_status, font=('Segoe UI', 10)).pack()
        ttk.Button(frame, text='New pairing code', command=self.rotate).pack(pady=8)
        self.enabled = tk.BooleanVar(value=False)
        ttk.Checkbutton(frame, text='3. Enable keyboard control', variable=self.enabled, command=self.set_mode).pack(anchor='w', pady=(5, 0))
        self.mode = tk.StringVar(value='Rehearsal: buttons send no keys.')
        ttk.Label(frame, textvariable=self.mode, wraplength=530).pack(anchor='w')
        actions = ttk.Frame(frame)
        actions.pack(fill='x', pady=(14, 8))
        ttk.Button(actions, text='Import existing deck', command=self.import_deck).pack(side='left')
        ttk.Button(actions, text='Disconnect phones', command=self.revoke).pack(side='right')
        ttk.Button(frame, text='Export deck for another PC', command=self.export_deck).pack(fill='x', pady=(4, 8))
        ttk.Label(frame, text='Keep this window open. Closing it stops all control.\nIf Windows asks, allow access only on your Private network.', wraplength=530, font=('Segoe UI', 10)).pack(anchor='w')
        self.tick()
        if open_browser and self.bridge_path.exists():
            self.bridge = MaisonBridge(self.bridge_path)

    def open_editor(self):
        try:
            if not webbrowser.open(self.admin_url):
                messagebox.showinfo('Open your PC controls', self.admin_url, parent=self.root)
        except OSError:
            messagebox.showinfo('Open your PC controls', self.admin_url, parent=self.root)

    def draw_qr(self):
        self.canvas.delete('all')
        if not self.url.get():
            self.canvas.create_text(108, 108, text='No network address found.\nConnect your PC to Wi-Fi\nor Ethernet, then restart.', justify='center', width=195)
            return
        qr = qrcode.QRCode(border=4, error_correction=qrcode.constants.ERROR_CORRECT_M)
        qr.add_data(self.url.get())  # No admin token or pairing code in the QR.
        qr.make(fit=True)
        matrix = qr.get_matrix()
        scale = 216 // len(matrix)
        offset = (216 - scale * len(matrix)) // 2
        for y, row in enumerate(matrix):
            for x, filled in enumerate(row):
                if filled:
                    self.canvas.create_rectangle(offset+x*scale, offset+y*scale, offset+(x+1)*scale, offset+(y+1)*scale, fill='black', outline='')

    def rotate(self):
        with self.state.lock:
            self.state.rotate()

    def revoke(self):
        with self.state.lock:
            self.state.sessions.clear()
            self.state.rotate()

    def set_mode(self):
        with self.state.lock:
            self.state.execute = bool(self.enabled.get())
        self.mode.set('Keyboard control is ON. Check LIVE Studio for actual app status.' if self.enabled.get() else 'Rehearsal: buttons send no keys.')

    def tick(self):
        try:
            success = self.bridge_messages.get_nowait()
            self.pairing_bridge = False
            self.maison_pair_button.configure(state='normal')
            if success:
                self.maison_code.set('')
                if self.bridge:
                    self.bridge.close()
                self.direct_enabled.set(False)
                self.bridge = MaisonBridge(self.bridge_path)
            else:
                self.maison_status.set('Pairing failed. Generate a new code in Maison > Deck and try again.')
        except queue.Empty:
            pass
        if self.bridge and not self.pairing_bridge:
            studio = self.bridge.studio.snapshot()
            self.maison_status.set(self.bridge.status + (' LIVE Studio ready.' if studio['connected'] else ' Waiting for LIVE Studio main screen.'))
        with self.state.lock:
            remaining = max(0, int(self.state.code_until-time.monotonic()))
            self.code.set(self.state.code if remaining else 'EXPIRED')
            self.pair_status.set(f'{len(self.state.sessions)} phone(s) paired · Code expires in {remaining//60}:{remaining%60:02d}')
        self.root.after(1000, self.tick)

    def pair_maison(self):
        if self.pairing_bridge:
            return
        code = self.maison_code.get().strip()
        self.pairing_bridge = True
        self.maison_pair_button.configure(state='disabled')
        self.maison_status.set('Pairing with Maison…')
        def work():
            try:
                enroll(self.bridge_path, code)
                self.bridge_messages.put(True)
            except (OSError, ValueError):
                self.bridge_messages.put(False)
        threading.Thread(target=work, daemon=True).start()

    def set_direct_mode(self):
        if self.bridge:
            self.bridge.enabled = self.direct_enabled.get()
        else:
            self.direct_enabled.set(False)
            self.maison_status.set('Connect to Maison first.')

    def import_deck(self):
        selected = filedialog.askopenfilename(parent=self.root, title='Choose your previous deck.json', filetypes=[('Deck configuration', '*.json')])
        if not selected:
            return
        try:
            config = validate(json.loads(Path(selected).read_text(encoding='utf-8')))
            if self.state.path.exists() and not messagebox.askyesno('Replace your deck?', 'Replace the current buttons with this file? A backup will be saved.', parent=self.root):
                return
            with self.state.lock:
                if self.state.path.exists():
                    backup = self.state.path.with_name('deck-backup-'+str(time.time_ns())+'.json')
                    backup.write_bytes(self.state.path.read_bytes())
            save_config(self.state, config)
            messagebox.showinfo('Deck imported', 'Your buttons are ready in the PC controls.', parent=self.root)
        except (OSError, ValueError, TypeError):
            messagebox.showerror('Cannot import deck', 'Choose a valid Lantern Deck JSON file. Your current buttons have not been replaced.', parent=self.root)

    def use_profile(self, audio_only):
        if not messagebox.askyesno('Set up your buttons', 'Replace the current deck with '+('two audio buttons' if audio_only else 'six studio buttons')+'? A backup will be saved. Keyboard control will return to rehearsal.', parent=self.root):
            return
        try:
            with self.state.lock:
                backup = self.state.path.with_name('deck-backup-'+str(time.time_ns())+'.json')
                backup.write_text(json.dumps(self.state.config, indent=2, ensure_ascii=False), encoding='utf-8')
                self.state.execute = False
            self.enabled.set(False)
            self.set_mode()
            save_config(self.state, studio_profile(audio_only))
            self.show_setup()
        except OSError:
            messagebox.showerror('Setup not saved', 'Could not save the deck or backup. Check the data folder permissions.', parent=self.root)

    def show_setup(self):
        with self.state.lock:
            lines = [b['label']+'  =  '+(b['shortcut'] or 'Not assigned') for b in self.state.config['buttons']]
        messagebox.showinfo('Link your buttons in LIVE Studio',
            'In LIVE Studio: Settings > Hotkeys > Use hotkeys ON.\n'
            'Click each matching action field and press its shortcut.\n\n'+ '\n'.join(lines)+
            '\n\nScenes: choose the action for each existing scene.\n'
            'Microphone: Audio > Mute / Unmute input device.\n'
            'Desktop sound: Audio > Mute / Unmute output device.\n'
            'Ending selects a scene, not Stop LIVE.\n\n'
            'Reopen Hotkeys to check the settings saved. Then pair your phone, '
            'enable keyboard control and test while offline. Check mute and scene '
            'status in LIVE Studio; the deck cannot read it.\n\n'
            'On another PC: choose Full studio or import your exported deck, '
            'assign matching TikTok hotkeys there, and scan that PC’s QR code.', parent=self.root)

    def export_deck(self):
        selected = filedialog.asksaveasfilename(parent=self.root, title='Save deck for another PC', defaultextension='.json', initialfile='My-studio-deck.json', filetypes=[('Deck configuration', '*.json')])
        if selected:
            try:
                with self.state.lock:
                    Path(selected).write_text(json.dumps(self.state.config, indent=2, ensure_ascii=False), encoding='utf-8')
                messagebox.showinfo('Deck exported', 'Import this file on the other PC. Match the shortcuts in its LIVE Studio and pair using its QR code.', parent=self.root)
            except OSError:
                messagebox.showerror('Export failed', 'Choose a writable folder and try again.', parent=self.root)

    def close(self):
        if self.bridge:
            self.bridge.close()
        with self.state.lock:
            self.state.execute = False
        self.server.shutdown()
        self.server.server_close()
        self.root.destroy()


def self_test(report):
    """Exercise bundled assets, Tk, QR, pairing and mode switching without real key input."""
    result = {'ok': False}
    root = None
    server = None
    try:
        with tempfile.TemporaryDirectory() as temp:
            server, thread, ips = start_server(Path(temp)/'deck.json', '127.0.0.1', 0)
            root = tk.Tk()
            root.withdraw()
            app = Companion(root, server, ['127.0.0.1'], open_browser=False)
            root.update_idletasks()
            base = f'http://127.0.0.1:{server.server_port}'
            for asset in ('/', '/app.js', '/shortcuts.js', '/style.css'):
                with urllib.request.urlopen(base+asset, timeout=5) as response:
                    assert response.status == 200 and len(response.read()) > 100
            def call(route, token='', body=None):
                req = urllib.request.Request(base+route, data=None if body is None else json.dumps(body).encode(), headers={'Content-Type':'application/json', 'Authorization':'Bearer '+token})
                return json.load(urllib.request.urlopen(req, timeout=5))
            token = call('/api/pair', body={'code':server.state.code})['token']
            assert call('/api/state', token)['mode'] == 'rehearsal'
            app.enabled.set(True)
            app.set_mode()
            assert call('/api/state', token)['mode'] == 'keys enabled'
            app.enabled.set(False)
            app.set_mode()
            assert call('/api/state', token)['mode'] == 'rehearsal'
            save_config(server.state, server.state.config)
            assert State(server.state.path).config == server.state.config
            from unittest.mock import patch
            with patch.object(messagebox, 'askyesno', return_value=True), patch.object(messagebox, 'showinfo'):
                app.use_profile(True)
                assert server.state.config == studio_profile(True)
                assert not server.state.execute and not app.enabled.get()
                app.use_profile(False)
                assert server.state.config == studio_profile(False)
                exported = Path(temp) / 'export.json'
                with patch.object(filedialog, 'asksaveasfilename', return_value=str(exported)):
                    app.export_deck()
                assert validate(json.loads(exported.read_text(encoding='utf-8'))) == studio_profile(False)
                assert len(list(server.state.path.parent.glob('deck-backup-*.json'))) == 2
            assert len(app.canvas.find_all()) > 20
            app.revoke()
            assert not server.state.sessions
            result = {'ok':True, 'checks':['bundled HTML/CSS/JS', 'hidden Tk window', 'QR rendering', 'pairing', 'mode switch without re-pairing', 'configuration persistence', 'two/six button setup', 'backup and export', 'revocation'], 'real_keys_sent':False}
    except Exception as exc:
        result = {'ok':False, 'error':repr(exc)}
    finally:
        if server:
            server.shutdown()
            server.server_close()
        if root:
            root.destroy()
        report.write_text(json.dumps(result, indent=2), encoding='utf-8')
    return 0 if result['ok'] else 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--self-test', type=Path)
    args = parser.parse_args()
    if args.self_test:
        return self_test(args.self_test)
    root = tk.Tk()
    root.withdraw()
    try:
        directory = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'LanternDeck'
        directory.mkdir(parents=True, exist_ok=True)
        server, thread, ips = start_server(directory / 'deck.json')
        app = Companion(root, server, ips)
    except OSError as exc:
        messagebox.showerror('Lantern Deck could not start', 'Close any other Lantern Deck window and try again.\n\nIf it still fails, check that port 8765 is available and your app data folder is writable.\n\n'+str(exc), parent=root)
        root.destroy()
        return 1
    except (ValueError, TypeError):
        messagebox.showerror('Configuration needs attention', 'The saved deck is invalid. Your file has not been changed.\n\nRename deck.json in %LOCALAPPDATA%\\LanternDeck, then restart and import a valid backup.', parent=root)
        root.destroy()
        return 1
    root.deiconify()
    root.mainloop()
    return 0


if __name__ == '__main__':
    sys.exit(main())
