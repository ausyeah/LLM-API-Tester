"""生成应用图标：暖纸底测速仪表盘，多尺寸 .ico + 预览 .png。

用法: python tools/make_icon.py
输出: assets/app.ico（16~256 多尺寸）、assets/app.png（256 预览）
"""
import math
import os
import sys
from io import BytesIO

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image

from PySide6.QtCore import QBuffer, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen
from PySide6.QtWidgets import QApplication

SIZES = [16, 24, 32, 48, 64, 128, 256]

# 配色与应用一致：纸面 + 赭红指针 + 暖黑描边
FACE = "#f7f2e8"
RING = "#2e2a24"
TRACK = "#ded7c7"
ARC = "#b14e2d"
TICK = "#8f8779"
NEEDLE = "#2e2a24"
TEXT = "#8f8779"


def draw(size: int) -> QImage:
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    s = size / 256.0

    cx, cy, r = 128 * s, 134 * s, 100 * s

    # 外圈 + 表盘
    p.setPen(QPen(QColor(RING), 8 * s))
    p.setBrush(QColor(FACE))
    p.drawEllipse(QPointF(cx, cy), r, r)

    # 弧形轨道（240°，起点左下 210°，顺时针到 -30°）
    track_rect = QRectF(cx - 72 * s, cy - 72 * s, 144 * s, 144 * s)
    p.setPen(QPen(QColor(TRACK), 14 * s, Qt.PenStyle.SolidLine,
                  Qt.PenCapStyle.RoundCap))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawArc(track_rect, 210 * 16, -240 * 16)

    # 已「跑过」的赭红弧（表示高速区）
    p.setPen(QPen(QColor(ARC), 14 * s, Qt.PenStyle.SolidLine,
                  Qt.PenCapStyle.RoundCap))
    p.drawArc(track_rect, 210 * 16, -190 * 16)

    # 主刻度
    p.setPen(QPen(QColor(TICK), 6 * s, Qt.PenStyle.SolidLine,
                  Qt.PenCapStyle.RoundCap))
    for i in range(7):
        deg = 210 - i * 40  # 每 40° 一格
        rad = math.radians(deg)
        x1 = cx + 56 * s * math.cos(rad)
        y1 = cy - 56 * s * math.sin(rad)
        x2 = cx + 42 * s * math.cos(rad)
        y2 = cy - 42 * s * math.sin(rad)
        p.drawLine(QPointF(x1, y1), QPointF(x2, y2))

    # 指针（指向上方偏右的高速区）
    deg = 55
    rad = math.radians(deg)
    nx = cx + 62 * s * math.cos(rad)
    ny = cy - 62 * s * math.sin(rad)
    tail = 18 * s
    p.setPen(QPen(QColor(NEEDLE), 9 * s, Qt.PenStyle.SolidLine,
                  Qt.PenCapStyle.RoundCap))
    p.drawLine(QPointF(cx - tail * math.cos(rad), cy + tail * math.sin(rad)),
               QPointF(nx, ny))

    # 轴心
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(ARC))
    p.drawEllipse(QPointF(cx, cy), 15 * s, 15 * s)
    p.setBrush(QColor(FACE))
    p.drawEllipse(QPointF(cx, cy), 5 * s, 5 * s)

    # ms 字样
    p.setPen(QColor(TEXT))
    p.setFont(QFont("Microsoft YaHei UI", int(22 * s), QFont.Weight.Bold))
    p.drawText(QRectF(cx - 40 * s, cy + 28 * s, 80 * s, 34 * s),
               Qt.AlignCenter, "ms")

    p.end()
    return img


def main():
    app = QApplication.instance() or QApplication([])
    out_dir = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "assets")
    os.makedirs(out_dir, exist_ok=True)

    pngs = {}
    for size in SIZES:
        img = draw(size)
        buf = QBuffer()
        buf.open(QBuffer.OpenModeFlag.WriteOnly)
        img.save(buf, "PNG")
        pngs[size] = Image.open(BytesIO(bytes(buf.data()))).convert("RGBA")

    ico_path = os.path.join(out_dir, "app.ico")
    pngs[256].save(ico_path, format="ICO",
                   sizes=[(sz, sz) for sz in SIZES])
    pngs[256].save(os.path.join(out_dir, "app.png"))
    print("saved:", ico_path)


if __name__ == "__main__":
    main()
