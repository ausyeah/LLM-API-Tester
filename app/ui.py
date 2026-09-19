"""主界面：纸感卡片 + 统一无衬线字体 + 浅色/深色/跟随系统。"""
from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QDrag, QKeySequence
from PySide6.QtCore import QMimeData
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QFormLayout, QFrame, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMenu, QMessageBox,
    QFileDialog,
    QProxyStyle, QPushButton, QScrollArea, QSpinBox, QStyle, QTableWidget,
    QTableWidgetItem, QToolButton, QVBoxLayout, QWidget,
)

from . import catalog, config, history, tester, theme
from .history_dialog import HistoryDialog
from .models import ModelRow
from .net import validate_base_url
from .taskman import TaskManager


def chip(text: str, tooltip: str = "", accent: bool = False) -> QLabel:
    lab = QLabel(text)
    lab.setObjectName("chip-accent" if accent else "chip")
    lab.setAlignment(Qt.AlignmentFlag.AlignCenter)
    if tooltip:
        lab.setToolTip(tooltip)
    return lab


def muted(text: str) -> QLabel:
    lab = QLabel(text)
    lab.setObjectName("muted")
    return lab


class CopyableTable(QTableWidget):
    """Ctrl+C 复制选中单元格；多单元格按表格形状用制表符拼接。"""

    @staticmethod
    def _text_of(item):
        return item.data(Qt.ItemDataRole.UserRole) or item.text()

    def keyPressEvent(self, e):
        if e.matches(QKeySequence.StandardKey.Copy):
            items = self.selectedItems()
            if items:
                rows = sorted({i.row() for i in items})
                cols = sorted({i.column() for i in items})
                grid = {(i.row(), i.column()): self._text_of(i) for i in items}
                lines = ["\t".join(grid.get((r, c), "") for c in cols)
                         for r in rows]
                QApplication.clipboard().setText("\n".join(lines))
        else:
            super().keyPressEvent(e)


class DragKeyButton(QToolButton):
    """按住即可把明文 Key 拖到记事本/浏览器等其他窗口。"""

    def __init__(self, get_text, parent=None):
        super().__init__(parent)
        self.setText("拖动")
        self._get_text = get_text
        self.setToolTip("按住拖到其他窗口即可粘贴明文 Key")

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self._get_text():
            drag = QDrag(self)
            md = QMimeData()
            md.setText(self._get_text())
            drag.setMimeData(md)
            drag.exec(Qt.CopyAction)
        else:
            super().mousePressEvent(e)


class AsteriskMaskStyle(QProxyStyle):
    """把密码掩码的大圆点换成小星号 *（只影响显示，行为不变）。"""

    def styleHint(self, hint, option=None, widget=None, returnData=None):
        if hint == QStyle.StyleHint.SH_LineEdit_PasswordCharacter:
            return ord("*")
        return super().styleHint(hint, option, widget, returnData)


class KeyRow(QWidget):
    """API Key：掩码 + 显隐 + 复制 + 拖出。"""

    changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.edit = QLineEdit()
        self.edit.setEchoMode(QLineEdit.EchoMode.Password)
        # 无参代理：委托应用样式但不接管其所有权，避免控件销毁时全局样式被删
        self.edit.setStyle(AsteriskMaskStyle())
        self.edit.setPlaceholderText("sk-…（留空则不发送鉴权头）")
        self.edit.textEdited.connect(self.changed.emit)

        self.eye = QPushButton("显示")
        self.eye.setFixedWidth(56)
        self.eye.clicked.connect(self._toggle_echo)

        self.copy_btn = QPushButton("复制")
        self.copy_btn.setToolTip("复制明文 Key（掩码状态下复制的也是真 Key）")
        self.copy_btn.clicked.connect(self._copy)

        self.drag_btn = DragKeyButton(self.edit.text)
        self.drag_btn.setFixedWidth(56)

        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(6)
        h.addWidget(self.edit, 1)
        h.addWidget(self.eye)
        h.addWidget(self.copy_btn)
        h.addWidget(self.drag_btn)

    def _toggle_echo(self):
        masked = self.edit.echoMode() == QLineEdit.EchoMode.Password
        self.edit.setEchoMode(
            QLineEdit.EchoMode.Normal if masked else QLineEdit.EchoMode.Password)
        self.eye.setText("隐藏" if masked else "显示")

    def _copy(self):
        QApplication.clipboard().setText(self.edit.text())
        self.copy_btn.setText("已复制")
        QTimer.singleShot(1200, lambda: self.copy_btn.setText("复制"))


class ProviderItem(QWidget):
    """左侧列表项：编号徽章 + 名称 + 延迟/禁用状态 + 箭头。"""

    def __init__(self, index: int, provider, parent=None):
        super().__init__(parent)
        self.setObjectName("prov-row")
        self.num = QLabel(f"{index:02d}")
        self.num.setObjectName("numchip")
        self.num.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.name_lab = QLabel(provider.name or "(未命名)")
        self.name_lab.setObjectName("card-title")
        self.sub_lab = QLabel("")
        self.sub_lab.setObjectName("muted")
        chev = QLabel("›")
        chev.setObjectName("chevron")

        mid = QVBoxLayout()
        mid.setContentsMargins(0, 0, 0, 0)
        mid.setSpacing(1)
        mid.addWidget(self.name_lab)
        mid.addWidget(self.sub_lab)

        h = QHBoxLayout(self)
        h.setContentsMargins(10, 10, 10, 10)
        h.setSpacing(10)
        h.addWidget(self.num)
        h.addLayout(mid, 1)
        h.addWidget(chev)
        self.set_enabled(provider.enabled)
        if provider.last_conn:
            self.set_conn(provider.last_conn)

    def set_conn(self, r: dict):
        state = r.get("state", "")
        if state == "cancelled" or r.get("error") == "cancelled":
            self.sub_lab.setText("已取消")
            self.sub_lab.setStyleSheet(f"color: {theme.token('danger')};")
        elif state == "reachable_no_models":
            self.sub_lab.setText("可达 · 无模型列表")
            self.sub_lab.setStyleSheet(f"color: {theme.token('warning')};")
            self.sub_lab.setToolTip(r.get("detail", "")[:300])
        elif state == "rate_limited":
            self.sub_lab.setText("已限流")
            self.sub_lab.setStyleSheet(f"color: {theme.token('warning')};")
            self.sub_lab.setToolTip(r.get("detail", "")[:300])
        elif state == "auth_error":
            self.sub_lab.setText("鉴权失败")
            self.sub_lab.setStyleSheet(f"color: {theme.token('danger')};")
            self.sub_lab.setToolTip(r.get("detail", "")[:300])
        elif r.get("ok"):
            self.sub_lab.setText(f"{r['latency_ms']}ms · {r.get('detail', '')}")
            self.sub_lab.setStyleSheet(f"color: {theme.token('success')};")
        else:
            self.sub_lab.setText(r.get("error") or "失败")
            self.sub_lab.setStyleSheet(f"color: {theme.token('danger')};")
            self.sub_lab.setToolTip(r.get("detail", "")[:300])

    def set_enabled(self, enabled: bool):
        if not enabled:
            self.name_lab.setStyleSheet(f"color: {theme.token('muted')};")
            self.sub_lab.setText("已禁用")
            self.sub_lab.setStyleSheet(f"color: {theme.token('muted')};")
        else:
            self.name_lab.setStyleSheet("")


class AddProviderDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("添加供应商")
        self.setMinimumWidth(420)
        self.name = QLineEdit()
        self.url = QLineEdit()
        self.url.setPlaceholderText("https://api.example.com/v1")
        self.key = QLineEdit()
        self.key.setEchoMode(QLineEdit.EchoMode.Password)
        self.key.setStyle(AsteriskMaskStyle())
        self.proto = QComboBox()
        for pid, label in config.PROTOCOL_LABELS.items():
            self.proto.addItem(label, pid)
        form = QFormLayout(self)
        form.setContentsMargins(18, 16, 18, 16)
        form.setSpacing(10)
        form.addRow("名称", self.name)
        form.addRow("Base URL", self.url)
        form.addRow("API Key", self.key)
        form.addRow("API 格式", self.proto)
        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                               | QDialogButtonBox.StandardButton.Cancel)
        box.accepted.connect(self._accept)
        box.rejected.connect(self.reject)
        form.addRow(box)

    def _accept(self):
        if not self.name.text().strip():
            QMessageBox.warning(self, "提示", "名称不能为空")
            return
        err = validate_base_url(self.url.text())
        if err:
            QMessageBox.warning(self, "提示", err)
            return
        self.accept()


class AddModelDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("添加模型")
        self.setMinimumWidth(380)
        self.mid = QLineEdit()
        self.mid.setPlaceholderText("模型 id，如 glm-4.7（必填）")
        self.dname = QLineEdit()
        self.dname.setPlaceholderText("展示名（可留空，默认同 id）")
        form = QFormLayout(self)
        form.setContentsMargins(18, 16, 18, 16)
        form.setSpacing(10)
        form.addRow("模型 ID", self.mid)
        form.addRow("展示名", self.dname)
        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                               | QDialogButtonBox.StandardButton.Cancel)
        box.accepted.connect(self._accept)
        box.rejected.connect(self.reject)
        form.addRow(box)

    def _accept(self):
        if not self.mid.text().strip():
            QMessageBox.warning(self, "提示", "模型 ID 不能为空")
            return
        self.accept()


class SettingsDialog(QDialog):
    def __init__(self, settings: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.setMinimumWidth(460)
        self.theme = QComboBox()
        for value, label in (("system", "跟随系统"),
                             ("light", "浅色 · 纸感"),
                             ("dark", "深色 · 灰黑")):
            self.theme.addItem(label, value)
        cur = settings.get("theme", "system")
        idx = max(0, self.theme.findData(cur))
        self.theme.setCurrentIndex(idx)
        self.proxy = QLineEdit(settings.get("proxy", ""))
        self.proxy.setPlaceholderText("http://127.0.0.1:7897（留空直连）")
        self.max_tokens = QSpinBox()
        self.max_tokens.setRange(1, 65536)
        self.max_tokens.setValue(tester.effective_max_tokens(settings))
        self.max_tokens.setToolTip("首字测速请求的最大输出 Token，默认 8")
        self.skip_tls = QCheckBox("跳过 TLS 证书校验（不安全）")
        self.skip_tls.setChecked(bool(settings.get("skip_tls")))
        warn = QLabel("⚠ 跳过 TLS 校验会暴露于中间人攻击，仅用于排查证书问题。")
        warn.setObjectName("muted")
        form = QFormLayout(self)
        form.setContentsMargins(18, 16, 18, 16)
        form.setSpacing(10)
        form.addRow("外观", self.theme)
        form.addRow("HTTP 代理", self.proxy)
        form.addRow("最大输出 Token", self.max_tokens)
        form.addRow("", self.skip_tls)
        form.addRow("", warn)
        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                               | QDialogButtonBox.StandardButton.Cancel)
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        form.addRow(box)


class MainWindow(QMainWindow):
    def __init__(self, providers, settings):
        super().__init__()
        self.setWindowTitle("LLM API Tester")
        self.providers = providers
        self.settings = settings
        self.current: object | None = None
        self._row_of: dict[str, int] = {}
        self._editing_model_id: str | None = None
        self._sys_dark = theme.system_is_dark()

        self.taskman = TaskManager(self._snapshot_settings)
        self.taskman.start()

        root = QWidget()
        self.setCentralWidget(root)
        v = QVBoxLayout(root)
        v.setContentsMargins(20, 16, 20, 16)
        v.setSpacing(12)
        v.addLayout(self._build_topbar())
        v.addLayout(self._build_body(), 1)

        self._wire_signals()
        self._sort_providers(save=False)
        self._refresh_provider_list()
        self._select_initial()
        self.resize(1120, 740)
        self.setMinimumSize(960, 640)

        self._theme_timer = QTimer(self)
        self._theme_timer.setInterval(2000)
        self._theme_timer.timeout.connect(self._poll_system_theme)
        self._theme_timer.start()

    # ---------- 顶栏 ----------
    def _build_topbar(self) -> QHBoxLayout:
        h = QHBoxLayout()
        h.setSpacing(8)
        titles = QVBoxLayout()
        titles.setSpacing(0)
        title = QLabel("LLM API Tester")
        title.setObjectName("app-title")
        sub = QLabel("供应商连通 · 模型列表 · 首字延迟")
        sub.setObjectName("app-subtitle")
        titles.addWidget(title)
        titles.addWidget(sub)

        self.btn_all_conn = QPushButton("全部测连通")
        self.btn_all_conn.setObjectName("btn-primary")
        self.btn_all_conn.clicked.connect(self.on_all_connectivity)
        self.btn_batch_ttft = QPushButton("测当前全部首字")
        self.btn_batch_ttft.setToolTip("真实调用当前供应商的全部模型（最大输出 Token 取设置值），可能计费")
        self.btn_batch_ttft.clicked.connect(self.on_batch_ttft)
        self.btn_cancel = QPushButton("取消任务")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self.taskman.cancel_current)

        self.spin_conc = QSpinBox()
        self.spin_conc.setRange(1, 8)
        self.spin_conc.setValue(int(self.settings.get("concurrency", 3)))
        self.spin_conc.setPrefix("并发 ")
        self.spin_conc.valueChanged.connect(self._on_conc_changed)
        self.spin_timeout = QSpinBox()
        self.spin_timeout.setRange(1, 120)
        self.spin_timeout.setSuffix("s")
        self.spin_timeout.setValue(int(self.settings.get("timeout_s", 10)))
        self.spin_timeout.setPrefix("超时 ")
        self.spin_timeout.valueChanged.connect(self._on_timeout_changed)

        self.btn_history = QPushButton("历史")
        self.btn_history.setToolTip("查看测速历史记录与延迟图表")
        self.btn_history.clicked.connect(self.on_history)
        self.btn_settings = QPushButton("设置")
        self.btn_settings.clicked.connect(self.on_settings)

        self.status_lab = muted("")

        h.addLayout(titles)
        h.addSpacing(16)
        h.addWidget(self.btn_all_conn)
        h.addWidget(self.btn_batch_ttft)
        h.addWidget(self.btn_cancel)
        h.addSpacing(6)
        h.addWidget(self.spin_conc)
        h.addWidget(self.spin_timeout)
        h.addStretch(1)
        h.addWidget(self.status_lab)
        h.addWidget(self.btn_history)
        h.addWidget(self.btn_settings)
        return h

    # ---------- 主体 ----------
    def _build_body(self) -> QHBoxLayout:
        h = QHBoxLayout()
        h.setSpacing(12)

        left = QFrame()
        left.setObjectName("card")
        left.setFixedWidth(268)
        lv = QVBoxLayout(left)
        lv.setContentsMargins(14, 14, 14, 12)
        lv.setSpacing(8)

        head = QHBoxLayout()
        head.setSpacing(6)
        diamond = QLabel("◆")
        diamond.setObjectName("kicker")
        self._diamond = diamond
        sect = QLabel("供应商")
        sect.setObjectName("card-title")
        self.provider_count = muted("")
        self.btn_sort = QPushButton("↑ 正序")
        self.btn_sort.setFixedHeight(28)
        self.btn_sort.setToolTip("按名称排序，再点一次切换正序/反序")
        self.btn_sort.clicked.connect(self._toggle_provider_sort)
        head.addWidget(diamond)
        head.addWidget(sect)
        head.addStretch(1)
        head.addWidget(self.provider_count)
        head.addWidget(self.btn_sort)
        lv.addLayout(head)

        self.provider_list = QListWidget()
        self.provider_list.setObjectName("providers")
        self.provider_list.currentRowChanged.connect(self._on_select_row)
        lv.addWidget(self.provider_list, 1)
        btn_add = QPushButton("添加供应商")
        btn_add.clicked.connect(self.on_add_provider)
        lv.addWidget(btn_add)
        h.addWidget(left)

        self.detail_scroll = QScrollArea()
        self.detail_scroll.setWidgetResizable(True)
        self.detail_scroll.setFrameShape(QFrame.Shape.NoFrame)
        h.addWidget(self.detail_scroll, 1)
        return h

    # ---------- 右侧详情 ----------
    def _build_detail(self, p) -> QWidget:
        wrap = QWidget()
        outer = QVBoxLayout(wrap)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(12)

        hero = QFrame()
        hero.setObjectName("card")
        hv = QVBoxLayout(hero)
        hv.setContentsMargins(18, 16, 18, 16)
        hv.setSpacing(10)

        top = QHBoxLayout()
        kicker = QLabel("当前供应商")
        kicker.setObjectName("kicker")
        self.chk_enabled = QCheckBox("已启用")
        self.chk_enabled.setChecked(p.enabled)
        self.chk_enabled.toggled.connect(self._on_enabled_toggled)
        top.addWidget(kicker)
        top.addStretch(1)
        top.addWidget(self.chk_enabled)
        hv.addLayout(top)

        name_row = QHBoxLayout()
        self.ed_name = QLineEdit(p.name)
        self.ed_name.setStyleSheet("font-size: 18px; padding: 6px 10px;")
        self.ed_name.textEdited.connect(self._on_name_edited)
        self.btn_toggle = QPushButton("禁用" if p.enabled else "启用")
        self.btn_toggle.clicked.connect(self._on_toggle_enabled)
        btn_del = QPushButton("删除供应商")
        btn_del.setObjectName("btn-danger")
        btn_del.clicked.connect(self.on_delete_provider)
        name_row.addWidget(self.ed_name, 1)
        name_row.addWidget(self.btn_toggle)
        name_row.addWidget(btn_del)
        hv.addLayout(name_row)
        hv.addWidget(muted("点这里编辑名称 · 测速会真实调用模型，可能计费"))
        outer.addWidget(hero)

        card = QFrame()
        card.setObjectName("card")
        v = QVBoxLayout(card)
        v.setContentsMargins(18, 16, 18, 16)
        v.setSpacing(12)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(10)

        self.ed_url = QLineEdit(p.base_url)
        self.ed_url.setPlaceholderText(
            "https://api.example.com/v1（OpenAI 格式没写 /v1 会自动补）")
        self.ed_url.textEdited.connect(self._on_url_edited)
        form.addRow("Base URL", self.ed_url)

        self.key_row = KeyRow()
        self.key_row.edit.setText(p.api_key)
        self.key_row.changed.connect(self._on_key_changed)
        form.addRow("API Key", self.key_row)

        self.cb_proto = QComboBox()
        for pid, label in config.PROTOCOL_LABELS.items():
            self.cb_proto.addItem(label, pid)
        self.cb_proto.setCurrentIndex(
            max(0, list(config.PROTOCOL_LABELS).index(p.protocol)))
        self.cb_proto.activated.connect(self._on_proto_changed)
        form.addRow("API 格式", self.cb_proto)

        conn_row = QHBoxLayout()
        self.btn_conn = QPushButton("测试连接")
        self.btn_conn.setObjectName("btn-primary")
        self.btn_conn.clicked.connect(self.on_test_connection)
        self.conn_lab = muted("")
        conn_row.addWidget(self.btn_conn)
        conn_row.addWidget(self.conn_lab, 1)
        form.addRow("", conn_row)
        v.addLayout(form)

        mhead = QHBoxLayout()
        diamond = QLabel("◆")
        diamond.setObjectName("kicker")
        title = QLabel("模型列表")
        title.setObjectName("card-title")
        self.btn_fetch = QPushButton("获取模型")
        self.btn_fetch.clicked.connect(self.on_fetch_models)
        self.btn_add_model = QPushButton("添加模型")
        self.btn_add_model.clicked.connect(self.on_add_model)
        self.btn_export_history = QPushButton("导出记录")
        self.btn_export_history.clicked.connect(self.on_export_history)
        self.progress_lab = muted("")
        mhead.addWidget(diamond)
        mhead.addWidget(title)
        mhead.addSpacing(8)
        mhead.addWidget(self.btn_fetch)
        mhead.addWidget(self.btn_add_model)
        mhead.addWidget(self.btn_export_history)
        mhead.addWidget(self.progress_lab, 1)
        v.addLayout(mhead)

        # 模型编辑面板（点 ✏ 展开，对齐参考图的行内编辑）
        self.model_editor = QFrame()
        self.model_editor.setObjectName("card")
        self.model_editor.setVisible(False)
        ev = QVBoxLayout(self.model_editor)
        ev.setContentsMargins(14, 12, 14, 12)
        ev.setSpacing(8)
        erow1 = QHBoxLayout()
        erow1.setSpacing(8)
        self.ed_model_name = QLineEdit()
        self.ed_model_name.setPlaceholderText("展示名")
        self.ed_model_ctx = QLineEdit()
        self.ed_model_ctx.setPlaceholderText("上下文：1M / 200K / 204800")
        self.ed_model_ctx.setFixedWidth(210)
        self.btn_editor_save = QPushButton("✓ 保存")
        self.btn_editor_save.setObjectName("btn-primary")
        self.btn_editor_save.clicked.connect(self._on_editor_save)
        self.btn_editor_cancel = QPushButton("× 取消")
        self.btn_editor_cancel.clicked.connect(
            lambda: self.model_editor.setVisible(False))
        erow1.addWidget(self.ed_model_name, 1)
        erow1.addWidget(self.ed_model_ctx)
        erow1.addWidget(self.btn_editor_save)
        erow1.addWidget(self.btn_editor_cancel)
        ev.addLayout(erow1)
        erow2 = QHBoxLayout()
        erow2.setSpacing(6)
        erow2.addWidget(muted("输入模式"))
        self._mod_buttons = []
        for key, label in (("text", "T 文本"), ("image", "图像"),
                           ("audio", "音频"), ("video", "视频"), ("pdf", "PDF")):
            b = QPushButton(label)
            b.setCheckable(True)
            self._mod_buttons.append((key, b))
            erow2.addWidget(b)
        erow2.addSpacing(4)
        erow2.addWidget(muted("留空则跟随对照表与接口返回"), 1)
        ev.addLayout(erow2)
        v.addWidget(self.model_editor)

        self.table = CopyableTable(0, 4)
        self.table.setHorizontalHeaderLabels(
            ["模型", "输入模式", "首字结果", "操作"])
        hh = self.table.horizontalHeader()
        # 模型列固定宽度可拖动；余量全部给首字结果（长文本多）
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setColumnWidth(0, 200)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QTableWidget.EditTriggers.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._table_menu)
        self.table.itemDoubleClicked.connect(self._copy_cell)
        self.table.verticalHeader().setDefaultSectionSize(48)
        v.addWidget(self.table, 1)
        outer.addWidget(card, 1)

        self._rebuild_table()
        return wrap

    def _rebuild_table(self):
        p = self.current
        self.table.setRowCount(0)
        self._row_of.clear()
        if not p:
            return
        self.table.setRowCount(len(p.models))
        muted_c = QColor(theme.token("muted"))
        ok_c = QColor(theme.token("success"))
        warn_c = QColor(theme.token("warning"))
        fail_c = QColor(theme.token("danger"))
        for i, m in enumerate(p.models):
            # 合并列：展示名为主行；与 ID 不同时才用小字补 ID
            name_w = QWidget()
            name_w.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            nv = QVBoxLayout(name_w)
            nv.setContentsMargins(2, 4, 2, 4)
            nv.setSpacing(0)
            top = QLabel(m.display_name or m.id)
            top.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            nv.addWidget(top)
            if m.display_name and m.display_name != m.id:
                sub = QLabel(m.id)
                sub.setObjectName("muted")
                sub.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
                nv.addWidget(sub)
            self.table.setCellWidget(i, 0, name_w)
            # item 不带文字（避免与组件叠画重影），ID 存 UserRole 供复制
            id_item = QTableWidgetItem("")
            id_item.setData(Qt.ItemDataRole.UserRole, m.id)
            id_item.setToolTip("双击复制模型 ID；右键有更多复制选项")
            if m.manual:
                id_item.setToolTip("手动添加：不会被「获取模型」冲掉。双击复制模型 ID")
            self.table.setItem(i, 0, id_item)

            meta = catalog.resolve(m.id, m.api_meta, m.meta_over)
            badge_w = QWidget()
            bh = QHBoxLayout(badge_w)
            bh.setContentsMargins(2, 0, 2, 0)
            bh.setSpacing(4)
            icons = {"text": "T", "image": "图", "audio": "听",
                     "video": "视", "pdf": "PDF"}
            order = {"text": 0, "image": 1, "audio": 2, "video": 3, "pdf": 4}
            mods = sorted(meta["mod"], key=lambda x: order.get(x, 9))
            for mod in mods:
                bh.addWidget(chip(icons.get(mod, mod)))
            ctx_text = catalog.format_ctx(meta["ctx"])
            if ctx_text:
                bh.addWidget(chip(ctx_text, tooltip=f"上下文长度 {meta['ctx']}"))
            if meta["think"]:
                bh.addWidget(chip("想", tooltip="思考档位: " + "/".join(meta["think"]),
                                  accent=True))
            bh.addStretch(1)
            self.table.setCellWidget(i, 1, badge_w)

            if m.result is not None:
                text, ok, warn = tester.format_ttft_result(m.result)
                res_item = QTableWidgetItem(text)
                color = warn_c if warn else (ok_c if ok else fail_c)
                res_item.setForeground(color)
                tip = (m.result.get("detail") or "")[:300]
                if m.result.get("requested_model"):
                    tip = (f"请求: {m.result['requested_model']} · "
                           f"上游返回: {m.result.get('reported_model') or '未报告'}"
                           f"（{m.result.get('model_match')}）\n") + tip
                res_item.setToolTip(tip)
                self.table.setItem(i, 2, res_item)
            else:
                self.table.setItem(i, 2, QTableWidgetItem(""))

            ops = QWidget()
            oh = QHBoxLayout(ops)
            oh.setContentsMargins(2, 0, 2, 0)
            oh.setSpacing(4)
            btn_speed = QToolButton()
            btn_speed.setObjectName("btn-speed")
            btn_speed.setText("⚡")
            btn_speed.setToolTip("测这条的首字延迟（真实调用，可能计费）")
            btn_speed.clicked.connect(lambda _, mid=m.id: self.on_row_speed(mid))
            btn_edit = QToolButton()
            btn_edit.setText("✏")
            btn_edit.setToolTip("编辑展示名 / 上下文 / 输入模式")
            btn_edit.clicked.connect(lambda _, mid=m.id: self.on_edit_model(mid))
            btn_del = QToolButton()
            btn_del.setObjectName("btn-danger")
            btn_del.setText("删除")
            btn_del.clicked.connect(lambda _, mid=m.id: self.on_del_model(mid))
            oh.addWidget(btn_speed)
            oh.addWidget(btn_edit)
            oh.addWidget(btn_del)
            self.table.setCellWidget(i, 3, ops)
            self._row_of[m.id] = i

    # ---------- 供应商列表 ----------
    def _sort_providers(self, save: bool = True):
        reverse = self.settings.get("provider_sort") == "name_desc"
        self.providers.sort(key=lambda p: (p.name or "").casefold(), reverse=reverse)
        if reverse:
            self.btn_sort.setText("↓ 反序")
        else:
            self.btn_sort.setText("↑ 正序")
        if save:
            self._save()

    def _toggle_provider_sort(self):
        cur = self.settings.get("provider_sort", "name_asc")
        self.settings["provider_sort"] = (
            "name_asc" if cur == "name_desc" else "name_desc")
        self._sort_providers()
        self._refresh_provider_list()

    def _refresh_provider_list(self):
        sel_id = self.current.id if self.current else None
        self.provider_list.blockSignals(True)
        self.provider_list.clear()
        n = len(self.providers)
        self.provider_count.setText(f"共 {n} 家")
        for i, p in enumerate(self.providers):
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, p.id)
            self.provider_list.addItem(item)
            w = ProviderItem(i, p)
            hint = w.sizeHint()
            item.setSizeHint(QSize(max(hint.width(), 200),
                                   max(hint.height(), 56)))
            self.provider_list.setItemWidget(item, w)
            if p.id == sel_id:
                self.provider_list.setCurrentItem(item)
        self.provider_list.blockSignals(False)

    def _select_initial(self):
        last = self.settings.get("last_provider")
        for row, p in enumerate(self.providers):
            if p.id == last:
                self.provider_list.setCurrentRow(row)
                return
        if self.providers:
            self.provider_list.setCurrentRow(0)
        else:
            self._show_empty_detail()

    def _provider_by_id(self, pid: str):
        for p in self.providers:
            if p.id == pid:
                return p
        return None

    def _on_select_row(self, row: int):
        if 0 <= row < len(self.providers):
            self._set_current(self.providers[row])
        else:
            self._set_current(None)

    def _set_current(self, p):
        self.current = p
        self.settings["last_provider"] = p.id if p else None
        self._save()
        if p:
            self.detail_scroll.setWidget(self._build_detail(p))
        else:
            self._show_empty_detail()

    def _show_empty_detail(self):
        lab = QLabel("左侧添加一个供应商开始使用")
        lab.setObjectName("muted")
        lab.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lab.setStyleSheet("font-size: 15px;")
        self.detail_scroll.setWidget(lab)

    # ---------- 供应商编辑 ----------
    def _on_name_edited(self, text: str):
        if self.current:
            self.current.name = text
            self._save()
            self._refresh_provider_list()

    def _on_url_edited(self, text: str):
        if self.current:
            self.current.base_url = text.strip()
            self._save()

    def _on_key_changed(self, text: str):
        if self.current:
            self.current.api_key = text
            self._save()

    def _on_proto_changed(self, index: int):
        if self.current:
            self.current.protocol = self.cb_proto.currentData()
            self._save()

    def _on_enabled_toggled(self, checked: bool):
        if self.current:
            self.current.enabled = checked
            self.btn_toggle.setText("禁用" if checked else "启用")
            self._save()
            self._refresh_provider_list()

    def _on_toggle_enabled(self):
        if self.current:
            self.chk_enabled.setChecked(not self.current.enabled)

    def on_delete_provider(self):
        p = self.current
        if not p:
            return
        if QMessageBox.question(
                self, "确认", f"删除供应商「{p.name}」？其配置与模型列表将一并删除。"
        ) != QMessageBox.StandardButton.Yes:
            return
        self.providers.remove(p)
        self.current = None
        self._save()
        self._refresh_provider_list()
        if self.providers:
            self.provider_list.setCurrentRow(0)
        else:
            self._set_current(None)

    def on_add_provider(self):
        dlg = AddProviderDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        p = config.new_provider(
            name=dlg.name.text().strip(),
            base_url=dlg.url.text().strip(),
            api_key=dlg.key.text(),
            protocol=dlg.proto.currentData(),
        )
        self.providers.append(p)
        self._sort_providers()
        self._refresh_provider_list()
        for i, x in enumerate(self.providers):
            if x.id == p.id:
                self.provider_list.setCurrentRow(i)
                break

    # ---------- 连通 / 模型 / 测速 ----------
    def on_test_connection(self):
        p = self.current
        if not p:
            return
        err = validate_base_url(p.base_url)
        if err:
            self._set_conn_label(False, err)
            return
        self.conn_lab.setText("测试中…")
        self.conn_lab.setStyleSheet(f"color: {theme.token('muted')};")
        self.taskman.test_connectivity(p)

    def on_fetch_models(self):
        p = self.current
        if not p:
            return
        if self.taskman.is_provider_busy(p.id):
            QMessageBox.information(self, "提示", "该供应商正在批量测速，请稍候")
            return
        self.progress_lab.setText("获取模型中…")
        self.taskman.fetch_models(p)

    def on_add_model(self):
        p = self.current
        if not p:
            return
        dlg = AddModelDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        mid = dlg.mid.text().strip()
        if p.model_by_id(mid):
            QMessageBox.information(self, "提示", f"模型 {mid} 已存在")
            return
        p.models.append(ModelRow(id=mid,
                                 display_name=dlg.dname.text().strip(),
                                 manual=True))
        self._save()
        self._rebuild_table()

    def on_history(self):
        HistoryDialog(self.providers, self._save, self).exec()

    def on_export_history(self):
        p = self.current
        if not p:
            return
        if not p.history:
            QMessageBox.information(self, "提示", "当前供应商还没有测速记录")
            return
        default_name = f"{p.name or 'provider'}-测速记录.csv"
        path, _ = QFileDialog.getSaveFileName(
            self, "导出测速记录", default_name, "CSV 文件 (*.csv)")
        if not path:
            return
        try:
            history.export_csv(p.history, path)
        except Exception as e:
            self.status_lab.setText(f"导出失败: {e}")
            return
        self.status_lab.setText(f"已导出 {len(p.history)} 条测速记录")

    def on_edit_model(self, mid: str):
        p = self.current
        if not p:
            return
        m = p.model_by_id(mid)
        if not m:
            return
        self._editing_model_id = mid
        meta = catalog.resolve(m.id, m.api_meta, m.meta_over)
        self.ed_model_name.setText(m.display_name or m.id)
        self.ed_model_ctx.setText(catalog.format_ctx(meta["ctx"]) or "")
        for key, b in self._mod_buttons:
            b.setChecked(key in meta["mod"])
        self.model_editor.setVisible(True)

    def _on_editor_save(self):
        p = self.current
        mid = self._editing_model_id
        if not p or not mid:
            return
        m = p.model_by_id(mid)
        if not m:
            return
        m.display_name = self.ed_model_name.text().strip()
        ctx = catalog.parse_ctx(self.ed_model_ctx.text())
        mods = [key for key, b in self._mod_buttons if b.isChecked()]
        over: dict = {}
        if ctx:
            over["ctx"] = ctx
        if mods:
            over["mod"] = mods
        m.meta_over = over
        self._save()
        self.model_editor.setVisible(False)
        self._rebuild_table()

    def on_del_model(self, mid: str):
        p = self.current
        if not p:
            return
        m = p.model_by_id(mid)
        if m:
            p.models.remove(m)
            if self._editing_model_id == mid:
                self._editing_model_id = None
                self.model_editor.setVisible(False)
            self._save()
            self._rebuild_table()

    # ---------- 复制 ----------
    def _copy_text(self, text: str, label: str = "已复制"):
        QApplication.clipboard().setText(text)
        self.status_lab.setText(f"{label}：{text[:60]}")

    def _copy_cell(self, item):
        value = CopyableTable._text_of(item) if item is not None else ""
        if value:
            header = self.table.horizontalHeaderItem(item.column())
            self._copy_text(value,
                            f"已复制{header.text() if header else '内容'}")

    def _table_menu(self, pos):
        menu = QMenu(self)
        p = self.current
        item = self.table.itemAt(pos)
        if p and item is not None:
            mid = next((mid for mid, r in self._row_of.items()
                        if r == item.row()), None)
            m = p.model_by_id(mid) if mid else None
            if m:
                menu.addAction("复制模型 ID",
                               lambda: self._copy_text(m.id, "已复制模型 ID"))
                menu.addAction("复制展示名",
                               lambda: self._copy_text(m.name, "已复制展示名"))
                if m.result is not None:
                    text, _, _ = tester.format_ttft_result(m.result)
                    menu.addAction("复制首字结果",
                                   lambda: self._copy_text(text, "已复制首字结果"))
                menu.addAction("复制整行（制表符分隔）",
                               lambda: self._copy_text(f"{m.name}\t{m.id}",
                                                       "已复制整行"))
                menu.addSeparator()
        act_all = menu.addAction("复制全部模型 ID（每行一个）",
                                 self._copy_all_ids)
        act_all.setEnabled(bool(p and p.models))
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _copy_all_ids(self):
        p = self.current
        if p and p.models:
            self._copy_text("\n".join(m.id for m in p.models),
                            f"已复制 {len(p.models)} 个模型 ID")

    def on_row_speed(self, mid: str):
        p = self.current
        if not p:
            return
        if self.taskman.is_provider_busy(p.id):
            QMessageBox.information(self, "提示", "该供应商正在批量测速，请稍候")
            return
        if not self.taskman.test_single_ttft(p, mid):
            return
        row = self._row_of.get(mid)
        if row is not None:
            item = QTableWidgetItem("测速中…")
            item.setForeground(QColor(theme.token("muted")))
            self.table.setItem(row, 2, item)

    def on_all_connectivity(self):
        if not self.taskman.test_all_connectivity(self.providers):
            QMessageBox.information(self, "提示", "已有批量任务在运行")
        else:
            self.status_lab.setText("批量测连通中…")

    def on_batch_ttft(self):
        p = self.current
        if not p:
            QMessageBox.information(self, "提示", "请先选择供应商")
            return
        if not p.models:
            QMessageBox.information(
                self, "提示", "当前供应商没有模型，请先「获取模型」或手动添加")
            return
        ret = QMessageBox.question(
            self, "确认测速",
            f"将真实调用「{p.name}」下的 {len(p.models)} 个模型\n"
            f"(max_tokens={tester.effective_max_tokens(self.settings)}，默认关思考)，"
            "可能产生少量费用。继续？")
        if ret != QMessageBox.StandardButton.Yes:
            return
        if not self.taskman.test_provider_ttft(p):
            QMessageBox.information(self, "提示", "已有批量任务在运行")
        else:
            self.progress_lab.setText("测速中 0/" + str(len(p.models)))
            self.status_lab.setText("批量测首字中…")

    def on_settings(self):
        dlg = SettingsDialog(self.settings, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        self.settings["proxy"] = dlg.proxy.text().strip()
        self.settings["skip_tls"] = dlg.skip_tls.isChecked()
        self.settings["max_tokens"] = dlg.max_tokens.value()
        self.settings["theme"] = dlg.theme.currentData()
        self._save()
        self._apply_theme()

    def _apply_theme(self):
        theme.apply(QApplication.instance(), self.settings.get("theme", "system"))
        self._sys_dark = theme.system_is_dark()
        self._refresh_provider_list()
        if self.current:
            self._set_current(self.current)
        else:
            self._show_empty_detail()

    def _poll_system_theme(self):
        if self.settings.get("theme", "system") != "system":
            return
        dark = theme.system_is_dark()
        if dark != self._sys_dark:
            self._apply_theme()

    # ---------- 任务信号 ----------
    def _wire_signals(self):
        self.taskman.conn_result.connect(self._on_conn_result)
        self.taskman.models_fetched.connect(self._on_models_fetched)
        self.taskman.ttft_result.connect(self._on_ttft_result)
        self.taskman.ttft_progress.connect(self._on_ttft_progress)
        self.taskman.batch_finished.connect(self.status_lab.setText)
        self.taskman.batch_changed.connect(self._on_batch_changed)

    def _on_conn_result(self, pid: str, r: dict):
        p = self._provider_by_id(pid)
        if not p:
            return
        p.last_conn = r
        self._refresh_provider_list()
        if self.current is p:
            self._set_conn_label(bool(r.get("ok")),
                                 self._conn_text(r), r.get("detail", ""),
                                 r.get("state", ""))

    @staticmethod
    def _conn_text(r: dict) -> str:
        state = r.get("state", "")
        if state == "cancelled" or r.get("error") == "cancelled":
            return "已取消"
        if state == "reachable_no_models":
            return f"可达 · 无模型列表 · {r.get('latency_ms', '?')}ms"
        if state == "auth_error":
            return f"鉴权失败 · HTTP {r.get('status', '?')}"
        if state == "rate_limited":
            return f"已限流 · HTTP {r.get('status', '?')}"
        if state == "server_error":
            return f"服务端错误 · HTTP {r.get('status', '?')}"
        if r.get("ok"):
            return f"HTTP {r['status']} · {r['latency_ms']}ms · {r.get('detail', '')}"
        return r.get("error") or "失败"

    def _set_conn_label(self, ok: bool, text: str, detail: str = "",
                        state: str = ""):
        self.conn_lab.setText(text)
        if state in {"reachable_no_models", "rate_limited"}:
            color = theme.token("warning")
        else:
            color = theme.token("success") if ok else theme.token("danger")
        self.conn_lab.setStyleSheet(f"color: {color};")
        self.conn_lab.setToolTip(detail[:300])

    def _on_models_fetched(self, pid: str, models, error: str):
        p = self._provider_by_id(pid)
        if not p:
            return
        if error:
            warning = error.startswith("WARN: ")
            message = error[6:] if warning else error
            self.progress_lab.setText(
                f"可达但无模型列表: {message}" if warning else f"获取失败: {message}")
            self.progress_lab.setStyleSheet(
                f"color: {theme.token('warning' if warning else 'danger')};")
            return
        existing = {m.id: m for m in p.models}
        added = 0
        for f in models or []:
            row = existing.get(f["id"])
            if row:
                if not row.manual:
                    row.api_meta = f.get("api_meta") or {}
                    if f.get("display_name"):
                        row.display_name = f["display_name"]
            else:
                p.models.append(ModelRow(id=f["id"],
                                         display_name=f.get("display_name", ""),
                                         api_meta=f.get("api_meta") or {}))
                added += 1
        self._save()
        if self.current is p:
            self._rebuild_table()
            self.progress_lab.setText(
                f"获取到 {len(models or [])} 个模型（新增 {added}，手动行已保留）")
            self.progress_lab.setStyleSheet(f"color: {theme.token('success')};")

    def _on_ttft_result(self, pid: str, mid: str, r: dict):
        p = self._provider_by_id(pid)
        if not p:
            return
        m = p.model_by_id(mid)
        if not m:
            return
        m.result = r
        p.history.append(history.make_record(p, m, r, self.settings))
        p.history = history.limit_records(p.history)
        self._save()
        if self.current is p:
            row = self._row_of.get(mid)
            if row is not None:
                text, ok, warn = tester.format_ttft_result(r)
                item = QTableWidgetItem(text)
                item.setForeground(QColor(theme.token(
                    "warning" if warn else ("success" if ok else "danger"))))
                tip = (r.get("detail") or "")[:300]
                if r.get("requested_model"):
                    tip = (f"请求: {r['requested_model']} · "
                           f"上游返回: {r.get('reported_model') or '未报告'}"
                           f"（{r.get('model_match')}）\n") + tip
                item.setToolTip(tip)
                self.table.setItem(row, 2, item)

    def _on_ttft_progress(self, pid: str, done: int, total: int, fails: int):
        if self.current and self.current.id == pid:
            self.progress_lab.setText(
                f"测速中 {done}/{total} · 成功 {done - fails} · 失败 {fails}")

    def _on_batch_changed(self):
        running = self.taskman.batch_running
        self.btn_all_conn.setEnabled(not running)
        self.btn_batch_ttft.setEnabled(not running)
        self.btn_cancel.setEnabled(running)

    # ---------- 设置 ----------
    def _snapshot_settings(self) -> dict:
        return dict(self.settings)

    def _on_conc_changed(self, v: int):
        self.settings["concurrency"] = v
        self._save()

    def _on_timeout_changed(self, v: int):
        self.settings["timeout_s"] = v
        self._save()

    def _save(self):
        try:
            config.save(self.providers, self.settings)
        except Exception as e:
            self.status_lab.setText(f"配置保存失败: {e}")

    def closeEvent(self, e):
        self._save()
        self.taskman.shutdown()
        super().closeEvent(e)
