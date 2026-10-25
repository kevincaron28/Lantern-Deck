"""Windows DPAPI: encrypt secrets so only this Windows user account can read them."""
import ctypes
from ctypes import wintypes
import os

ENTROPY = b'LanternDeck.Maison.v1'
CRYPTPROTECT_UI_FORBIDDEN = 0x1


class DATA_BLOB(ctypes.Structure):
    _fields_ = [('cbData', wintypes.DWORD), ('pbData', ctypes.POINTER(ctypes.c_char))]


def _blob(data):
    buffer = ctypes.create_string_buffer(data, len(data))
    return DATA_BLOB(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char))), buffer


def _apis():
    if os.name != 'nt':
        raise OSError('DPAPI requires Windows')
    crypt32 = ctypes.WinDLL('crypt32', use_last_error=True)
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    signature = [ctypes.POINTER(DATA_BLOB), wintypes.LPCWSTR, ctypes.POINTER(DATA_BLOB),
                 ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(DATA_BLOB)]
    crypt32.CryptProtectData.argtypes = signature
    crypt32.CryptProtectData.restype = wintypes.BOOL
    crypt32.CryptUnprotectData.argtypes = [ctypes.POINTER(DATA_BLOB), ctypes.POINTER(wintypes.LPWSTR)] + signature[2:]
    crypt32.CryptUnprotectData.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    return crypt32, kernel32


def _run(protecting, data):
    crypt32, kernel32 = _apis()
    source, _keep = _blob(data)
    entropy, _keep_entropy = _blob(ENTROPY)
    result = DATA_BLOB()
    if protecting:
        ok = crypt32.CryptProtectData(ctypes.byref(source), 'Lantern Deck', ctypes.byref(entropy),
                                      None, None, CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(result))
    else:
        ok = crypt32.CryptUnprotectData(ctypes.byref(source), None, ctypes.byref(entropy),
                                        None, None, CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(result))
    if not ok:
        raise OSError(ctypes.get_last_error(), 'DPAPI operation failed')
    try:
        return ctypes.string_at(result.pbData, result.cbData)
    finally:
        kernel32.LocalFree(ctypes.cast(result.pbData, ctypes.c_void_p))


def protect(data):
    return _run(True, data)


def unprotect(data):
    return _run(False, data)
