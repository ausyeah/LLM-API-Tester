"""TaskManager 冒烟（离屏）：批量连通 → 批量首字 → 中途取消，全管线过 Qt 信号。

Key 从环境变量读取：LLMTEST_OPENAI_KEY / LLMTEST_ANTHROPIC_KEY。
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from app.config import default_settings, new_provider
from app.models import ModelRow
from app.taskman import TaskManager


def build_providers():
    out = []
    key = os.environ.get("LLMTEST_OPENAI_KEY", "").strip()
    if key:
        p = new_provider(name="示例中转站", protocol="openai",
                         base_url="https://example.com/v1", api_key=key)
        out.append(p)
    key = os.environ.get("LLMTEST_ANTHROPIC_KEY", "").strip()
    if key:
        p = new_provider(name="GLM", protocol="anthropic",
                         base_url="https://api.z.ai/api/anthropic", api_key=key)
        out.append(p)
    return out


def main():
    providers = build_providers()
    if len(providers) < 2:
        sys.exit("需要 LLMTEST_OPENAI_KEY 与 LLMTEST_ANTHROPIC_KEY 两个环境变量")

    settings = default_settings()
    settings["concurrency"] = 3
    app = QApplication.instance() or QApplication([])
    tm = TaskManager(lambda: dict(settings))

    st = {"phase": 0, "conn": [], "ttft": [], "summaries": [],
          "cancel_at": None, "progress": []}

    def on_conn(pid, r):
        p = next(x for x in providers if x.id == pid)
        p.last_conn = r
        for m in r.get("models") or []:
            if not p.model_by_id(m["id"]):
                p.models.append(ModelRow(id=m["id"],
                                         display_name=m.get("display_name", "")))
        st["conn"].append({"pid": p.name, "ok": r.get("ok"),
                           "ms": r.get("latency_ms"), "err": r.get("error"),
                           "models": len(r.get("models") or [])})

    def on_ttft(pid, mid, r):
        st["ttft"].append({"pid": pid, "mid": mid, "ok": r.get("ok"),
                           "ttft_ms": r.get("ttft_ms"), "err": r.get("error")})
        if len(st["ttft"]) == 2 and st["phase"] == 1:
            st["cancel_at"] = len(st["ttft"])
            tm.cancel_current()

    def on_prog(pid, done, total, fails):
        st["progress"].append(f"{done}/{total}")

    def on_fin(summary):
        st["summaries"].append(summary)
        if st["phase"] == 0:
            st["phase"] = 1
            tm.test_provider_ttft(providers[-1])
        else:
            app.quit()

    tm.conn_result.connect(on_conn)
    tm.ttft_result.connect(on_ttft)
    tm.ttft_progress.connect(on_prog)
    tm.batch_finished.connect(on_fin)
    tm.start()
    tm.test_all_connectivity(providers)
    QTimer.singleShot(150000, app.quit)
    app.exec()
    tm.shutdown()

    print(json.dumps(st, ensure_ascii=False, indent=2))
    ok_conn = len(st["conn"]) == len(providers)
    ok_cancel = (st["cancel_at"] == 2
                 and any("取消" in s for s in st["summaries"][1:]))
    ok_ttft = len(st["ttft"]) >= 2 and any(t["ok"] for t in st["ttft"])
    print(f"\n批量连通: {'PASS' if ok_conn else 'FAIL'} · "
          f"批量首字+取消: {'PASS' if ok_cancel else 'FAIL'} · "
          f"TTFT有成功: {'PASS' if ok_ttft else 'FAIL'}")
    sys.exit(0 if (ok_conn and ok_cancel and ok_ttft) else 1)


if __name__ == "__main__":
    main()
