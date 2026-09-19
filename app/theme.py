"""主题系统：纸感浅色 / 灰黑深色 / 跟随系统。

全界面统一华文仿宋（有质感的衬线体）；深色只用黑灰，不用橙色。
"""
import winreg

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication

FONT = "'STFangsong', '华文仿宋', 'FangSong', '仿宋', 'Noto Serif SC', 'SimSun', serif"
FONT_NAME = "STFangsong"

LIGHT = {
    "window": "#f3f0e9", "surface": "#fcfbf8", "surface_alt": "#f1ede4",
    "border": "#e5dfd2", "text": "#2e2a24", "muted": "#8f8779",
    "accent": "#b14e2d", "accent_hover": "#9c4224", "accent_soft": "#f4e4dc",
    "on_accent": "#ffffff",
    "success": "#4a7c52", "warning": "#a06d1c", "danger": "#b04a3f",
    "danger_soft": "#f6e3e0",
    "chip_bg": "#efebe0", "chip_border": "#ded7c7", "input_bg": "#ffffff",
}

DARK = {
    "window": "#121212", "surface": "#1c1c1c", "surface_alt": "#262626",
    "border": "#333333", "text": "#e6e6e6", "muted": "#9a9a9a",
    "accent": "#d0d0d0", "accent_hover": "#ffffff", "accent_soft": "#2a2a2a",
    "on_accent": "#121212",
    "success": "#8fbf96", "warning": "#d0a54f", "danger": "#d07a73",
    "danger_soft": "#3a2a29",
    "chip_bg": "#2a2a2a", "chip_border": "#3a3a3a", "input_bg": "#171717",
}

CURRENT = dict(LIGHT)


def token(key: str) -> str:
    return CURRENT.get(key, "#ff0000")


def system_is_dark() -> bool:
    """读 Windows 深色模式注册表；读不到默认浅色。"""
    try:
        k = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
        v, _ = winreg.QueryValueEx(k, "AppsUseLightTheme")
        return v == 0
    except OSError:
        return False


_QSS = """
* { outline: none; }
QWidget { font-family: %(font)s; font-size: 14px; color: %(text)s; }
QMainWindow, QDialog { background: %(window)s; }
QLabel { background: transparent; font-family: %(font)s; }
QLabel#app-title { font-family: %(font)s; font-size: 20px; font-weight: 400; }
QLabel#app-subtitle { font-family: %(font)s; color: %(muted)s; font-size: 13px; }
QLabel#card-title { font-family: %(font)s; font-size: 16px; font-weight: 400; }
QLabel#muted { font-family: %(font)s; color: %(muted)s; font-size: 13px; }
QLabel#kicker { font-family: %(font)s; color: %(accent)s; font-size: 13px; }
QLabel#chevron { font-family: %(font)s; color: %(muted)s; font-size: 18px; }
QLabel#chip { font-family: %(font)s; background: %(chip_bg)s;
              border: 1px solid %(chip_border)s; border-radius: 6px;
              padding: 1px 7px; color: %(muted)s; font-size: 12px; }
QLabel#chip-accent { font-family: %(font)s; background: %(accent_soft)s;
                     border: 1px solid %(chip_border)s; border-radius: 6px;
                     padding: 1px 7px; color: %(text)s; font-size: 12px; }
QLabel#numchip { font-family: %(font)s; background: %(chip_bg)s; border-radius: 6px;
                 color: %(muted)s; font-size: 12px; min-width: 28px; max-width: 28px;
                 min-height: 20px; max-height: 20px; }
QFrame#card { background: %(surface)s; border: 1px solid %(border)s;
              border-radius: 14px; }
QWidget#prov-row { background: transparent; border-bottom: 1px solid %(border)s; }
QListWidget { background: transparent; border: none; font-family: %(font)s; }
QListWidget::item { color: %(text)s; }
QListWidget::item:selected { background: %(accent_soft)s; }
QPushButton { font-family: %(font)s; font-size: 14px; background: %(surface)s;
              border: 1px solid %(border)s; border-radius: 8px; padding: 5px 14px; }
QPushButton:hover { background: %(surface_alt)s; }
QPushButton:pressed { background: %(chip_bg)s; }
QPushButton:disabled { color: %(muted)s; background: %(chip_bg)s;
                       border-color: %(border)s; }
QPushButton#btn-primary { background: %(accent)s; color: %(on_accent)s;
                          border: 1px solid %(accent)s; }
QPushButton#btn-primary:hover { background: %(accent_hover)s;
                                border-color: %(accent_hover)s; }
QPushButton#btn-primary:disabled { background: %(chip_bg)s;
                                   border-color: %(chip_bg)s; color: %(muted)s; }
QPushButton#btn-danger { color: %(danger)s; }
QPushButton#btn-danger:hover { background: %(danger_soft)s; }
QPushButton:checked { background: %(accent_soft)s; border-color: %(accent)s;
                      color: %(accent)s; font-weight: 600; }
QPushButton:checked:hover { background: %(accent_soft)s; }
QToolButton { font-family: %(font)s; font-size: 14px; background: %(surface)s;
              border: 1px solid %(border)s; border-radius: 8px; padding: 3px 10px; }
QToolButton:hover { background: %(surface_alt)s; }
QToolButton:disabled { color: %(muted)s; }
QToolButton#btn-speed { border-radius: 12px; padding: 2px 9px; font-size: 14px; }
QToolButton#btn-speed:hover { background: %(accent_soft)s;
                              border-color: %(chip_border)s; }
QToolButton#btn-danger { color: %(danger)s; }
QToolButton#btn-danger:hover { background: %(danger_soft)s; }
QLineEdit, QComboBox, QSpinBox { font-family: %(font)s; font-size: 14px;
                                 background: %(input_bg)s;
                                 border: 1px solid %(border)s;
                                 border-radius: 8px; padding: 4px 8px;
                                 selection-background-color: %(accent_soft)s; }
QLineEdit:focus, QComboBox:focus, QSpinBox:focus { border-color: %(accent)s; }
QComboBox::drop-down { border: none; width: 20px; }
QSpinBox::up-button, QSpinBox::down-button { width: 16px; border: none;
                                             background: transparent; }
QTableWidget { font-family: %(font)s; font-size: 14px; background: transparent;
               border: none; gridline-color: transparent;
               alternate-background-color: %(surface_alt)s;
               selection-background-color: %(accent_soft)s;
               selection-color: %(text)s; }
QHeaderView::section { font-family: %(font)s; font-size: 13px;
                       background: %(surface)s; color: %(muted)s; border: none;
                       border-bottom: 1px solid %(border)s; padding: 6px; }
QTableCornerButton::section { background: %(surface)s; border: none; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: %(chip_border)s; border-radius: 4px;
                              min-height: 30px; }
QScrollBar::handle:vertical:hover { background: %(muted)s; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 2px; }
QScrollBar::handle:horizontal { background: %(chip_border)s; border-radius: 4px;
                                min-width: 30px; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
QScrollArea { background: transparent; border: none; }
QScrollArea > QWidget > QWidget { background: transparent; }
QMenu { font-family: %(font)s; font-size: 14px; background: %(surface)s;
        border: 1px solid %(border)s; border-radius: 10px; padding: 6px; }
QMenu::item { padding: 6px 20px 6px 12px; border-radius: 6px; }
QMenu::item:selected { background: %(accent_soft)s; }
QMenu::separator { height: 1px; background: %(border)s; margin: 5px 8px; }
QToolTip { font-family: %(font)s; font-size: 13px; background: %(surface)s;
           color: %(text)s; border: 1px solid %(border)s; padding: 4px 8px;
           border-radius: 6px; }
QCheckBox { font-family: %(font)s; font-size: 14px; spacing: 6px;
            background: transparent; }
QCheckBox::indicator { width: 16px; height: 16px; border: 1px solid %(border)s;
                       border-radius: 5px; background: %(input_bg)s; }
QCheckBox::indicator:checked { background: %(accent)s; border-color: %(accent)s; }
"""


def build_qss(p: dict) -> str:
    qss = dict(p)
    qss["font"] = FONT
    return _QSS % qss


def build_palette(p: dict) -> QPalette:
    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Window, QColor(p["window"]))
    pal.setColor(QPalette.ColorRole.WindowText, QColor(p["text"]))
    pal.setColor(QPalette.ColorRole.Base, QColor(p["surface"]))
    pal.setColor(QPalette.ColorRole.AlternateBase, QColor(p["surface_alt"]))
    pal.setColor(QPalette.ColorRole.Text, QColor(p["text"]))
    pal.setColor(QPalette.ColorRole.Button, QColor(p["surface"]))
    pal.setColor(QPalette.ColorRole.ButtonText, QColor(p["text"]))
    pal.setColor(QPalette.ColorRole.Highlight, QColor(p["accent_soft"]))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor(p["text"]))
    pal.setColor(QPalette.ColorRole.ToolTipBase, QColor(p["surface"]))
    pal.setColor(QPalette.ColorRole.ToolTipText, QColor(p["text"]))
    pal.setColor(QPalette.ColorRole.PlaceholderText, QColor(p["muted"]))
    return pal


def apply(app: QApplication, mode: str) -> bool:
    """mode: light | dark | system。应用后返回是否处于深色。"""
    dark = (mode == "dark") or (mode == "system" and system_is_dark())
    p = DARK if dark else LIGHT
    CURRENT.clear()
    CURRENT.update(p)
    app.setStyle("Fusion")
    app.setFont(QFont(FONT_NAME, 11))
    app.setPalette(build_palette(p))
    app.setStyleSheet(build_qss(p))
    return dark
