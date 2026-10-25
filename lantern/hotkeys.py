"""Keyboard shortcut grammar and the Windows SendInput bridge (hotkey fallback mode)."""
import ctypes
from ctypes import wintypes
import os
import re

MODS = {'CTRL': 0x11, 'ALT': 0x12, 'SHIFT': 0x10,
        'LEFTCTRL': 0xA2, 'RIGHTCTRL': 0xA3, 'LEFTALT': 0xA4, 'RIGHTALT': 0xA5,
        'LEFTSHIFT': 0xA0, 'RIGHTSHIFT': 0xA1}
# Side-specific modifiers are sent as physical scan codes (extended flag for right Ctrl/Alt).
MOD_SCANS = {0x11: (0x1D, False), 0xA2: (0x1D, False), 0xA3: (0x1D, True),
             0x12: (0x38, False), 0xA4: (0x38, False), 0xA5: (0x38, True),
             0x10: (0x2A, False), 0xA0: (0x2A, False), 0xA1: (0x36, False)}
KEYS = {**{chr(n): n for n in range(65, 91)}, **{str(n): 48 + n for n in range(10)},
        **{'F' + str(n): 0x6F + n for n in range(1, 25)},
        'SPACE': 0x20, 'ENTER': 0x0D, 'TAB': 9, 'ESC': 0x1B,
        'UP': 0x26, 'DOWN': 0x28, 'LEFT': 0x25, 'RIGHT': 0x27}
ARROWS = (0x25, 0x26, 0x27, 0x28)
ALIASES = {'LALT': 'LEFTALT', 'RALT': 'RIGHTALT', 'LCTRL': 'LEFTCTRL', 'RCTRL': 'RIGHTCTRL',
           'LSHIFT': 'LEFTSHIFT', 'RSHIFT': 'RIGHTSHIFT', 'CONTROL': 'CTRL',
           'LEFTCONTROL': 'LEFTCTRL', 'RIGHTCONTROL': 'RIGHTCTRL'}


def modifier_family(part):
    return part.removeprefix('LEFT').removeprefix('RIGHT')


def shortcut(value):
    """Normalize a shortcut such as 'ctrl + shift + 1' to 'CTRL+SHIFT+1'; '' means unassigned."""
    if not isinstance(value, str):
        raise ValueError('Shortcut must be text')
    if not value.strip():
        return ''
    parts = [ALIASES.get(p, p) for p in (re.sub(r'[ _-]', '', p).upper() for p in value.split('+'))]
    single = len(parts) == 1 and (parts[0] in MODS or re.fullmatch(r'F(?:[1-9]|1[0-9]|2[0-4])', parts[0]))
    families = [modifier_family(p) for p in parts[:-1]]
    chord = (len(parts) >= 2 and parts[-1] in KEYS and all(p in MODS for p in parts[:-1])
             and len(set(families)) == len(families))
    if not (single or chord):
        raise ValueError('Use a modifier plus a key, one modifier, or F1–F24')
    return '+'.join(parts)


def key_events(combo):
    """Return (virtual keys, [(vk, scan, flags), ...]) pressing in order and releasing in reverse."""
    codes = [MODS[p] if p in MODS else KEYS[p] for p in shortcut(combo).split('+')]

    def event(key, up=False):
        if key in MOD_SCANS:
            scan, extended = MOD_SCANS[key]
            return (0, scan, 8 | int(extended) | (2 if up else 0))
        return (key, 0, int(key in ARROWS) | (2 if up else 0))
    return codes, [event(k) for k in codes] + [event(k, True) for k in reversed(codes)]


def send_keys(combo):
    if os.name != 'nt':
        raise RuntimeError('Keyboard output requires Windows')

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [('wVk', wintypes.WORD), ('wScan', wintypes.WORD), ('dwFlags', wintypes.DWORD),
                    ('time', wintypes.DWORD), ('dwExtraInfo', ctypes.c_size_t)]

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [('dx', wintypes.LONG), ('dy', wintypes.LONG), ('mouseData', wintypes.DWORD),
                    ('dwFlags', wintypes.DWORD), ('time', wintypes.DWORD), ('dwExtraInfo', ctypes.c_size_t)]

    class HARDWAREINPUT(ctypes.Structure):
        _fields_ = [('uMsg', wintypes.DWORD), ('wParamL', wintypes.WORD), ('wParamH', wintypes.WORD)]

    class UNION(ctypes.Union):
        _fields_ = [('ki', KEYBDINPUT), ('mi', MOUSEINPUT), ('hi', HARDWAREINPUT)]

    class INPUT(ctypes.Structure):
        # The full union is required for the correct INPUT size on 64-bit Windows.
        _anonymous_ = ('u',)
        _fields_ = [('type', wintypes.DWORD), ('u', UNION)]

    api = ctypes.WinDLL('user32', use_last_error=True)
    api.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
    api.SendInput.restype = wintypes.UINT
    api.GetAsyncKeyState.argtypes = [ctypes.c_int]
    api.GetAsyncKeyState.restype = wintypes.SHORT
    codes, events = key_events(combo)
    if any(api.GetAsyncKeyState(k) & 0x8000 for k in set(codes + list(MODS.values()) + [0x5B, 0x5C])):
        raise RuntimeError('Release keyboard modifiers and shortcut keys, then retry')

    def make(vk, scan, flags):
        return INPUT(type=1, ki=KEYBDINPUT(wVk=vk, wScan=scan, dwFlags=flags))
    batch = (INPUT * len(events))(*[make(*e) for e in events])
    if api.SendInput(len(batch), batch, ctypes.sizeof(INPUT)) != len(batch):
        release = (INPUT * len(codes))(*[make(*e) for e in events[len(codes):]])
        api.SendInput(len(release), release, ctypes.sizeof(INPUT))
        raise RuntimeError('Windows did not accept all keys; check application privilege levels')
