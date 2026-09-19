"""历史记录面板：过滤 + 自绘图表（无新依赖）+ 明细表 + 导出/清空。

数据来自各 Provider.history（dict 记录，随 config.json 持久化）。
"""
from datetime import datetime

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import (
    QComboBox, QDialog, QFileDialog, QHBoxLayout, QHeaderView, QLabel,
    QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
    QWidget,
)

from . import history, theme


def _fmt_ts(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).astimezone().strftime("%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return (iso or "")[:19]


def _fmt_ms(v) -> str:
    if not isinstance(v, (int, float)):
        return "—"
    return f"{v:.0f}" if v >= 100 else f"{v:.1f}"


class ChartCanvas(QWidget):
    """自适应图：一组对象 → 条形图（平均值）；单个对象 → 时间趋势折线。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(230)
        self._title = ""
        self._stats = ""
        self._labels: list[str] = []
        self._values: list[float] = []
        self._mode = "bars"

    def set_data(self, title: str, labels: list[str], values: list[float],
                 mode: str, stats: str = ""):
        self._title, self._labels, self._values = title, labels, values
        self._mode, self._stats = mode, stats
        self.update()

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        text_c = QColor(theme.token("text"))
        muted_c = QColor(theme.token("muted"))
        border_c = QColor(theme.token("border"))
        accent_c = QColor(theme.token("accent"))

        p.setPen(muted_c)
        p.drawText(QRectF(12, 6, w - 24, 18), Qt.AlignLeft | Qt.AlignVCenter,
                   self._title)
        if self._stats:
            p.drawText(QRectF(12, 6, w - 24, 18), Qt.AlignRight | Qt.AlignVCenter,
                       self._stats)

        if not self._values:
            p.drawText(self.rect(), Qt.AlignCenter, "暂无数据")
            return

        left, right = 14.0, w - 14.0
        top, bottom = 34.0, h - 30.0
        p.setPen(QPen(border_c, 1))
        p.drawLine(int(left), int(bottom), int(right), int(bottom))
        fm = QFontMetrics(p.font())

        if self._mode == "line":
            n = len(self._values)
            lo, hi = min(self._values), max(self._values)
            pad = (hi - lo) * 0.15 or max(hi * 0.1, 1.0)
            ylo, yhi = lo - pad, hi + pad
            pts = []
            for i, v in enumerate(self._values):
                x = left + (right - left) * (i / max(n - 1, 1))
                y = bottom - (bottom - top) * (v - ylo) / (yhi - ylo)
                pts.append((x, y))
            p.setPen(QPen(accent_c, 2))
            for i in range(len(pts) - 1):
                p.drawLine(int(pts[i][0]), int(pts[i][1]),
                           int(pts[i + 1][0]), int(pts[i + 1][1]))
            p.setBrush(accent_c)
            p.setPen(Qt.NoPen)
            for x, y in pts:
                p.drawEllipse(QRectF(x - 3, y - 3, 6, 6))
            lx, ly = pts[-1]
            p.setPen(text_c)
            p.drawText(QRectF(lx - 40, ly - 22, 80, 16),
                       Qt.AlignCenter, _fmt_ms(self._values[-1]))
            p.setPen(muted_c)
            if self._labels:
                p.drawText(QRectF(left, bottom + 6, 140, 18),
                           Qt.AlignLeft, self._labels[0])
                p.drawText(QRectF(right - 140, bottom + 6, 140, 18),
                           Qt.AlignRight, self._labels[-1])
            return

        n = len(self._values)
        slot = (right - left) / max(n, 1)
        barw = max(10.0, min(46.0, slot * 0.6))
        maxv = max(self._values) or 1
        p.setBrush(accent_c)
        p.setPen(Qt.NoPen)
        for i, v in enumerate(self._values):
            bh = (bottom - top) * (v / maxv)
            x = left + slot * i + (slot - barw) / 2
            p.drawRoundedRect(QRectF(x, bottom - bh, barw, bh), 3, 3)
            p.setPen(muted_c)
            p.drawText(QRectF(x - 8, bottom - bh - 18, barw + 16, 16),
                       Qt.AlignCenter, _fmt_ms(v))
            p.setPen(muted_c)
            elided = fm.elidedText(self._labels[i], Qt.ElideRight, int(slot) - 2)
            p.drawText(QRectF(left + slot * i, bottom + 6, slot, 18),
                       Qt.AlignCenter, elided)


class HistoryDialog(QDialog):
    """测速历史：图表 + 明细。改动（清空）通过 on_change 回调持久化。"""

    def __init__(self, providers, on_change, parent=None):
        super().__init__(parent)
        self.setWindowTitle("测速历史")
        self.resize(900, 660)
        self._providers = list(providers)
        self._on_change = on_change

        v = QVBoxLayout(self)
        v.setContentsMargins(16, 14, 16, 14)
        v.setSpacing(10)

        filters = QHBoxLayout()
        self.cb_provider = QComboBox()
        self.cb_provider.addItem("全部供应商", None)
        for p in self._providers:
            self.cb_provider.addItem(p.name, p.name)
        self.cb_model = QComboBox()
        self.cb_model.addItem("全部模型", None)
        btn_export = QPushButton("导出 CSV")
        btn_clear = QPushButton("清空…")
        btn_close = QPushButton("关闭")
        filters.addWidget(QLabel("供应商"))
        filters.addWidget(self.cb_provider, 1)
        filters.addWidget(QLabel("模型"))
        filters.addWidget(self.cb_model, 1)
        filters.addWidget(btn_export)
        filters.addWidget(btn_clear)
        filters.addWidget(btn_close)
        v.addLayout(filters)

        self.summary = QLabel("")
        self.summary.setObjectName("muted")
        v.addWidget(self.summary)

        self.chart = ChartCanvas()
        v.addWidget(self.chart)

        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(
            ["时间", "供应商", "模型", "结果", "TTFT", "TTFB", "来源", "错误 / 备注"])
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(7, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTriggers.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        v.addWidget(self.table, 1)

        self.cb_provider.currentIndexChanged.connect(self._on_provider_changed)
        self.cb_model.currentIndexChanged.connect(self._refresh)
        btn_export.clicked.connect(self._export)
        btn_clear.clicked.connect(self._clear)
        btn_close.clicked.connect(self.accept)
        self._refresh()

    # ---------- 数据 ----------
    def _pool(self) -> list[dict]:
        pname = self.cb_provider.currentData()
        recs: list[dict] = []
        for p in self._providers:
            if pname and p.name != pname:
                continue
            recs.extend(p.history or [])
        recs.sort(key=lambda r: r.get("timestamp", ""))
        return recs

    def _on_provider_changed(self):
        pname = self.cb_provider.currentData()
        seen: dict[str, str] = {}
        for p in self._providers:
            if pname and p.name != pname:
                continue
            for r in p.history or []:
                mid = r.get("model_id", "")
                if mid and mid not in seen:
                    label = r.get("model") or mid
                    seen[mid] = label if label == mid else f"{label} ({mid})"
        self.cb_model.blockSignals(True)
        self.cb_model.clear()
        self.cb_model.addItem("全部模型", None)
        for mid, label in seen.items():
            self.cb_model.addItem(label, mid)
        self.cb_model.blockSignals(False)
        self._refresh()

    def _refresh(self):
        recs = self._pool()
        mkey = self.cb_model.currentData()
        if mkey:
            recs = [r for r in recs if r.get("model_id") == mkey]
        oks = [r for r in recs
               if r.get("ok") and isinstance(r.get("ttft_ms"), (int, float))]
        avg = (sum(r["ttft_ms"] for r in oks) / len(oks)) if oks else None
        parts = [f"共 {len(recs)} 条", f"成功 {len(oks)}",
                 f"失败 {len(recs) - len(oks)}"]
        if avg is not None:
            parts.append(f"平均 TTFT {_fmt_ms(avg)}ms")
        self.summary.setText(" · ".join(parts))

        if mkey:
            self.chart.set_data(
                f"{mkey} 首字延迟趋势（仅成功）",
                [_fmt_ts(r.get("timestamp", "")) for r in oks],
                [float(r["ttft_ms"]) for r in oks],
                "line", stats="")
        else:
            groups: dict[str, list] = {}
            for r in oks:
                groups.setdefault(r.get("model_id", "?"), []).append(r)
            ordered = sorted(groups.items(),
                             key=lambda kv: kv[1][-1].get("timestamp", ""))[-12:]
            labels = [k for k, _ in ordered]
            values = [sum(x["ttft_ms"] for x in rs) / len(rs)
                      for _, rs in ordered]
            self.chart.set_data("各模型平均首字延迟（仅成功，最近 12 个）",
                                labels, values, "bars",
                                stats=f"n={len(oks)}" if oks else "")

        rows = list(reversed(recs))[:300]
        self.table.setRowCount(len(rows))
        ok_c = QColor(theme.token("success"))
        fail_c = QColor(theme.token("danger"))
        for i, r in enumerate(rows):
            ok = bool(r.get("ok"))
            extra = ""
            rep = r.get("reported_model") or ""
            if rep and r.get("model_match") in ("mismatch", "suffix"):
                extra = f"上游返回 {rep}"
            note = " · ".join(x for x in ("" if ok else
                                          (r.get("error") or r.get("error_code") or "失败"),
                                          extra) if x)
            cells = [
                _fmt_ts(r.get("timestamp", "")),
                r.get("provider", ""),
                r.get("model") or r.get("model_id", ""),
                "成功" if ok else "失败",
                _fmt_ms(r.get("ttft_ms")),
                _fmt_ms(r.get("ttfb_ms")),
                r.get("source") or "",
                note,
            ]
            for j, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if j == 3:
                    item.setForeground(ok_c if ok else fail_c)
                if j == 7:
                    item.setToolTip(r.get("detail", "")[:300])
                self.table.setItem(i, j, item)

    # ---------- 动作 ----------
    def _export(self):
        recs = self._pool()
        mkey = self.cb_model.currentData()
        if mkey:
            recs = [r for r in recs if r.get("model_id") == mkey]
        if not recs:
            QMessageBox.information(self, "提示", "当前筛选下没有记录")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "导出测速记录", "测速记录.csv", "CSV 文件 (*.csv)")
        if not path:
            return
        try:
            history.export_csv(recs, path)
        except Exception as e:
            QMessageBox.warning(self, "导出失败", str(e))
            return
        QMessageBox.information(self, "导出完成", f"已导出 {len(recs)} 条记录")

    def _clear(self):
        pname = self.cb_provider.currentData()
        scope = f"供应商「{pname}」" if pname else "全部供应商"
        if QMessageBox.question(
                self, "确认清空",
                f"清空{scope}的测速历史？此操作不可恢复。"
        ) != QMessageBox.StandardButton.Yes:
            return
        for p in self._providers:
            if not pname or p.name == pname:
                p.history = []
        self._on_change()
        self._refresh()
