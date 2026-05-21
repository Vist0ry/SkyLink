import ctypes
import sys

_MUTEX_NAME = r"Local\SkyLink_SingleInstance_v1"
_ERROR_ALREADY_EXISTS = 183

_MB_OK = 0x00000000
_MB_ICONINFORMATION = 0x00000040
_MB_TOPMOST = 0x00040000

_mutex_handle = None


def acquire_single_instance() -> bool:
    global _mutex_handle
    if sys.platform != "win32":
        return True
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.CreateMutexW(None, True, _MUTEX_NAME)
    if not handle:
        return False
    _mutex_handle = handle
    return kernel32.GetLastError() != _ERROR_ALREADY_EXISTS


def notify_already_running() -> None:
    if sys.platform != "win32":
        return
    ctypes.windll.user32.MessageBoxW(
        None,
        "Приложение SkyLink уже запущено.\n\n"
        "Проверьте область уведомлений (трей) или закройте "
        "лишний экземпляр через «Выход».",
        "SkyLink",
        _MB_OK | _MB_ICONINFORMATION | _MB_TOPMOST,
    )
