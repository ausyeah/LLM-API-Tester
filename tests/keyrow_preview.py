"""渲染 KeyRow 验证星号掩码效果。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QStyle

from app.ui import AsteriskMaskStyle, KeyRow


def main():
    app = QApplication([])
    row = KeyRow()
    row.edit.setText("sk-example-key-for-mask-preview-1234567890")
    row.resize(520, 34)
    row.show()

    def grab():
        row.grab().save(os.path.join(os.path.dirname(__file__),
                                     "keyrow_preview.png"))
        hint = QStyle.StyleHint.SH_LineEdit_PasswordCharacter
        print("echo:", row.edit.echoMode())
        print("mask char:", chr(row.edit.style().styleHint(hint)))
        app.quit()

    QTimer.singleShot(400, grab)
    app.exec()


if __name__ == "__main__":
    main()
