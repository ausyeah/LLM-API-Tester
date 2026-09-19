"""LLM API Tester 入口。"""
import logging
import os
import sys
import ctypes
from pathlib import Path


_QT_DLL_HANDLES = []
_QT_PRELOADED_DLLS = []


def _prepare_frozen_qt_runtime():
    if not getattr(sys, "frozen", False):
        return

    meipass = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    roots = (meipass, meipass / "_internal")
    dll_paths = []
    plugin_path = None
    for root in roots:
        for package_name in ("PySide6", "shiboken6"):
            package_path = root / package_name
            if not package_path.is_dir() or package_path in dll_paths:
                continue
            dll_paths.append(package_path)
            _QT_DLL_HANDLES.append(os.add_dll_directory(str(package_path)))
            os.environ["PATH"] = str(package_path) + os.pathsep + os.environ.get("PATH", "")
            if package_name == "PySide6" and (package_path / "plugins").is_dir():
                plugin_path = package_path / "plugins"

    if plugin_path is not None:
        os.environ["QT_PLUGIN_PATH"] = str(plugin_path)

    if sys.platform == "win32":
        system_icu = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "icuuc.dll"
        if system_icu.is_file():
            _QT_PRELOADED_DLLS.append(ctypes.WinDLL(str(system_icu)))


_prepare_frozen_qt_runtime()

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from app import config, theme
from app.ui import MainWindow

LOG_PATH = os.path.join(config.CONFIG_DIR, "app.log")
os.makedirs(config.CONFIG_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[logging.FileHandler(LOG_PATH, encoding="utf-8"),
              logging.StreamHandler()],
)


def app_icon() -> QIcon:
    """源码跑用项目 assets；打包后从 _MEIPASS 解包目录取。"""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(base, "assets", "app.ico")
    return QIcon(path) if os.path.exists(path) else QIcon()


def main():
    app = QApplication(sys.argv)
    app.setWindowIcon(app_icon())
    providers, settings = config.load()
    theme.apply(app, settings.get("theme", "system"))
    win = MainWindow(providers, settings)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
