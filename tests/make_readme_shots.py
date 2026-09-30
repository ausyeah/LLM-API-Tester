"""为 README 生成界面截图（离屏渲染，不修改应用源码）。

- 使用独立的 APPDATA 沙箱，绝不触碰用户真实配置
- 通过 monkeypatch 覆盖字体（本机没装 STFangsong）与主题为浅色
- 数据为**脱敏的代表性样例**：不含任何真实 Key、真实域名或真实主机信息
"""
import os
import sys
import datetime

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

SANDBOX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_shotdata")
os.environ["APPDATA"] = SANDBOX
# offscreen 插件不加载系统字体库（families 为 0），中文会全是豆腐块，
# 所以手动把中文字体注册进 font database，再把应用字体栈指过去。
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402
from PySide6.QtGui import QFontDatabase  # noqa: E402

from app import theme  # noqa: E402

_FONT_FILES = ["C:/Windows/Fonts/simsun.ttc", "C:/Windows/Fonts/msyh.ttc",
               "C:/Windows/Fonts/simhei.ttf", "C:/Windows/Fonts/Deng.ttf"]


def register_cjk_fonts():
    """必须在 QApplication 存在之后调用，否则会崩。"""
    loaded = []
    for f in _FONT_FILES:
        if os.path.exists(f):
            i = QFontDatabase.addApplicationFont(f)
            if i >= 0:
                loaded += QFontDatabase.applicationFontFamilies(i)
    pick = next((n for n in ("STFangsong", "FangSong", "SimSun",
                             "Microsoft YaHei UI", "Microsoft YaHei")
                 if n in loaded), None)
    if pick:
        theme.FONT_NAME = pick
        theme.FONT = f"'{pick}', serif"
    return pick

from app import config  # noqa: E402
from app.models import ModelRow, Provider  # noqa: E402
from app.ui import MainWindow  # noqa: E402

OUT = os.path.join(REPO, "docs", "screenshots")


def _ttft(ms, ok=True, **kw):
    r = {"ok": ok, "ttft_ms": ms, "ttfb_ms": int(ms * 0.42), "status": 200,
         "source": "text", "max_tokens": 8, "note": "", "error": "",
         "reported_model": "", "model_match": "", "detail": ""}
    r.update(kw)
    return r


def _rec(p, m, ms, **kw):
    r = _ttft(ms, **kw)
    return {"timestamp": datetime.datetime.now(datetime.timezone.utc)
            .isoformat(timespec="seconds"), "provider": p, "model": m,
            "model_id": m, "protocol": "openai", "max_tokens": 8,
            "ok": r["ok"], "state": r.get("state", ""), "error_code": "",
            "ttft_ms": r["ttft_ms"], "ttfb_ms": r["ttfb_ms"], "status": 200,
            "source": r["source"], "note": r["note"], "error": r["error"],
            "detail": "", "reported_model": r["reported_model"],
            "model_match": r["model_match"]}


def build_demo():
    """构造一组脱敏的代表性样例数据。"""
    ps = []

    p1 = Provider(id="demo-relay", name="某中转站", base_url="https://relay.example.com/v1",
                  api_key="sk-demo-0000", protocol="openai", note="示例数据 · 非真实站点")
    for mid, dn, ttft in [
        ("gpt-4o", "GPT-4o", 412),
        ("gpt-4o-mini", "GPT-4o mini", 289),
        ("claude-sonnet-4-5", "Claude Sonnet 4.5", 638),
        ("glm-5.2", "GLM-5.2", 351),
    ]:
        p1.models.append(ModelRow(id=mid, display_name=dn, result=_ttft(ttft)))
    # 演示「上游偷偷换模型」：请求 A、返回 B，触发琥珀色警示
    p1.models.append(ModelRow(
        id="deepseek-v3.2", display_name="DeepSeek-V3.2",
        result=_ttft(524, reported_model="deepseek-v3.1",
                     model_match="mismatch",
                     requested_model="deepseek-v3.2",
                     detail="上游返回: deepseek-v3.1（mismatch）")))
    p1.models.append(ModelRow(
        id="qwen3-max", display_name="Qwen3-Max",
        result=_ttft(0, ok=False, state="timeout", error="首字超时")))
    p1.last_conn = {"ok": True, "status": 200, "latency_ms": 182,
                    "state": "ok", "detail": "HTTP 200 · 12 个模型"}
    ps.append(p1)

    p2 = Provider(id="demo-glm", name="GLM", base_url="https://api.example.com/api/anthropic",
                  api_key="", protocol="anthropic", note="Anthropic Messages 协议")
    for mid, dn, ttft in [("glm-5.3-flash", "GLM-5.3-Flash", 297),
                          ("glm-4.7", "GLM-4.7", 445)]:
        p2.models.append(ModelRow(id=mid, display_name=dn, result=_ttft(ttft)))
    p2.last_conn = {"ok": True, "status": 200, "latency_ms": 96,
                    "state": "ok", "detail": "HTTP 200 · 8 个模型"}
    ps.append(p2)

    p3 = Provider(id="demo-local", name="本地 vLLM", base_url="http://127.0.0.1:8000",
                  api_key="", protocol="openai", note="无鉴权头", enabled=False)
    p3.models.append(ModelRow(id="qwen2.5-7b", display_name="Qwen2.5-7B"))
    ps.append(p3)

    # 给历史面板塞一点记录
    p1.history = [_rec("某中转站", n, t) for n, t in
                  [("GPT-4o", 468), ("GLM-5.2", 402), ("DeepSeek-V3.2", 588),
                   ("GPT-4o", 431), ("Claude Sonnet 4.5", 655), ("GLM-5.2", 388),
                   ("GPT-4o mini", 301), ("GPT-4o", 455), ("GLM-5.2", 419)]]
    p2.history = [_rec("GLM", n, t) for n, t in
                  [("GLM-5.3-Flash", 288), ("GLM-4.7", 471), ("GLM-5.3-Flash", 305)]]
    return ps, {"theme": "light", "concurrency": 3, "timeout_s": 10,
                "max_tokens": 8, "last_provider": "demo-relay",
                "provider_sort": "name_asc", "skip_tls": False, "proxy": ""}


def main():
    os.makedirs(OUT, exist_ok=True)
    providers, settings = build_demo()
    config.save(providers, settings)          # 落在沙箱里

    app = QApplication.instance() or QApplication([])
    picked = register_cjk_fonts()
    print("font in use:", picked)
    theme.apply(app, "light")                # 强制浅色「纸感」主题
    win = MainWindow(providers, settings)
    win.resize(1180, 720)
    win.show()

    shots = []

    def grab_main():
        p = os.path.join(OUT, "01-main.png")
        win.grab().save(p)
        shots.append(p)

    def grab_history():
        from app.history_dialog import HistoryDialog
        dlg = HistoryDialog(providers, lambda: None, win)
        dlg.resize(1080, 620)
        dlg.show()
        app.processEvents()

        def save():
            p = os.path.join(OUT, "02-history.png")
            dlg.grab().save(p)
            shots.append(p)
            dlg.close()
            app.quit()
        QTimer.singleShot(600, save)

    def step2():
        grab_history()

    def step1():
        grab_main()
        QTimer.singleShot(300, step2)

    QTimer.singleShot(1200, step1)
    app.exec()
    try:
        win.taskman.shutdown()
    except Exception:
        pass

    for p in shots:
        print("saved:", p, os.path.getsize(p) if os.path.exists(p) else "MISSING")


if __name__ == "__main__":
    main()
