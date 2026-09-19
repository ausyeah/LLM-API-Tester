"""Windows DPAPI 加密（ctypes，无第三方依赖）。

密文带 dpapi: 前缀存进配置文件；不带前缀的旧值按明文兼容读回。
非 Windows 环境退化为 base64（仅便于开发调试，正式打包只跑在 Windows）。
"""
import base64
import ctypes
import sys
from ctypes import wintypes

_PREFIX = "dpapi:"
_CRYPTPROTECT_UI_FORBIDDEN = 0x01


class _DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD),
                ("pbData", ctypes.POINTER(ctypes.c_char))]


def _blob(data: bytes) -> _DATA_BLOB:
    buf = ctypes.create_string_buffer(data, len(data))
    return _DATA_BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))


def _free(ptr) -> None:
    ctypes.windll.kernel32.LocalFree(ptr)


def protect(text: str) -> str:
    data = text.encode("utf-8")
    if sys.platform != "win32":
        return "b64:" + base64.b64encode(data).decode()
    cin, cout = _blob(data), _DATA_BLOB()
    try:
        if not ctypes.windll.crypt32.CryptProtectData(
                ctypes.byref(cin), None, None, None, None,
                _CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(cout)):
            raise OSError("CryptProtectData 失败")
        return _PREFIX + base64.b64encode(
            ctypes.string_at(cout.pbData, cout.cbData)).decode()
    finally:
        _free(cout.pbData)


def unprotect(token: str) -> str:
    if token.startswith("b64:"):
        return base64.b64decode(token[4:]).decode("utf-8")
    if not token.startswith(_PREFIX):
        return token
    raw = base64.b64decode(token[len(_PREFIX):])
    cin, cout = _blob(raw), _DATA_BLOB()
    try:
        if not ctypes.windll.crypt32.CryptUnprotectData(
                ctypes.byref(cin), None, None, None, None,
                _CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(cout)):
            raise OSError("CryptUnprotectData 失败")
        return ctypes.string_at(cout.pbData, cout.cbData).decode("utf-8")
    finally:
        _free(cout.pbData)
