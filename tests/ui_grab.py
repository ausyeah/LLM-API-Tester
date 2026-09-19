"""离屏渲染主窗口并保存截图（自检布局用）。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from app import config, theme
from app.ui import MainWindow


def main():
    app = QApplication.instance() or QApplication([])
    providers, settings = config.load()
    theme.apply(app, settings.get("theme", "light"))
    win = MainWindow(providers, settings)
    win.show()
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui_preview.png")

    def grab():
        win.grab().save(out)
        print("saved:", out)
        app.quit()

    QTimer.singleShot(900, grab)
    app.exec()
    win.taskman.shutdown()


if __name__ == "__main__":
    main()
