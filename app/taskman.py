"""任务调度：后台 asyncio 线程 + Qt 信号回传（界面不卡）。

约束（需求 3.4/4）：全软件同一时刻只跑一个批量任务；
批量 TTFT 期间同一供应商的单行测速被拒，其他供应商不受影响。
"""
import asyncio
import concurrent.futures
import logging
import threading

from PySide6.QtCore import QObject, QThread, Signal

from . import tester
from .net import make_client
from .protocols import get_protocol


log = logging.getLogger(__name__)


class _LoopThread(QThread):
    def __init__(self, on_ready, parent=None):
        super().__init__(parent)
        self._on_ready = on_ready

    def run(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._on_ready(loop)
        loop.run_forever()


class TaskManager(QObject):
    conn_result = Signal(str, object)          # provider_id, 连通结果
    models_fetched = Signal(str, object, str)  # provider_id, models|None, error
    ttft_result = Signal(str, str, object)     # provider_id, model_id, 结果
    ttft_progress = Signal(str, int, int, int) # provider_id, done, total, fails
    batch_finished = Signal(str)               # 汇总文本
    batch_changed = Signal()                   # 批量任务有无变化

    def __init__(self, get_settings):
        super().__init__()
        self._get_settings = get_settings
        self.loop: asyncio.AbstractEventLoop | None = None
        self.batch_running = False
        self._provider_busy: set[str] = set()
        self._cancel_evt: asyncio.Event | None = None
        self._batch_future = None
        self._ready = threading.Event()
        self._thread = _LoopThread(self._on_loop_ready)

    def _on_loop_ready(self, loop):
        self.loop = loop
        self._ready.set()

    # ---- 生命周期 ----
    def start(self):
        self._thread.start()
        self._ready.wait(5)

    def shutdown(self):
        if self._batch_future is not None:
            self._batch_future.cancel()
        if self.loop:
            self.loop.call_soon_threadsafe(self.loop.stop)
        self._thread.wait(2000)

    def submit(self, coro):
        if self.loop is not None:
            future = asyncio.run_coroutine_threadsafe(coro, self.loop)
            future.add_done_callback(self._on_future_done)
            return future
        coro.close()
        return None

    @staticmethod
    def _on_future_done(future):
        try:
            future.result()
        except (asyncio.CancelledError, concurrent.futures.CancelledError):
            return
        except Exception as exc:
            log.error("后台任务异常: %s", type(exc).__name__)

    # ---- 状态查询 ----
    def is_provider_busy(self, pid: str) -> bool:
        return pid in self._provider_busy

    # ---- 单发任务 ----
    def test_connectivity(self, provider):
        self.submit(self._conn_one(provider))

    async def _conn_one(self, provider):
        settings = self._get_settings()
        try:
            async with make_client(settings) as client:
                r = await tester.test_connectivity(
                    client, provider, get_protocol(provider.protocol), settings)
        except Exception as exc:
            r = tester.failure_from_exception(
                exc, float(settings.get("timeout_s", 10)), provider.api_key)
        self.conn_result.emit(provider.id, r)

    def fetch_models(self, provider):
        self.submit(self._fetch_models(provider))

    async def _fetch_models(self, provider):
        settings = self._get_settings()
        try:
            async with make_client(settings) as client:
                r = await tester.test_connectivity(
                    client, provider, get_protocol(provider.protocol), settings)
        except Exception as exc:
            r = tester.failure_from_exception(
                exc, float(settings.get("timeout_s", 10)), provider.api_key)
        self.conn_result.emit(provider.id, r)
        if r.get("ok"):
            self.models_fetched.emit(provider.id, r["models"], "")
        else:
            prefix = "WARN: " if r.get("state") == "reachable_no_models" else ""
            self.models_fetched.emit(
                provider.id, None,
                f"{prefix}{r.get('error', '')} {r.get('detail', '')[:200]}".strip())

    def test_single_ttft(self, provider, model_id: str) -> bool:
        if self.is_provider_busy(provider.id):
            return False
        self.submit(self._ttft_single(provider, model_id))
        return True

    async def _ttft_single(self, provider, model_id):
        settings = self._get_settings()
        try:
            async with make_client(settings) as client:
                r = await tester.run_ttft(
                    client, provider, get_protocol(provider.protocol), model_id, settings)
        except Exception as exc:
            r = tester.failure_from_exception(
                exc, float(settings.get("timeout_s", 10)), provider.api_key,
                tester.effective_max_tokens(settings))
        self.ttft_result.emit(provider.id, model_id, r)

    # ---- 批量任务 ----
    def test_all_connectivity(self, providers) -> bool:
        if self.batch_running:
            return False
        enabled = [p for p in providers if p.enabled]
        self._begin_batch()
        self._batch_future = self.submit(self._conn_batch(enabled))
        return True

    async def _conn_batch(self, providers):
        settings = self._get_settings()
        sem = asyncio.Semaphore(int(settings.get("concurrency", 3)))
        results = []
        cancel = self._cancel_evt

        async def one(p):
            async with sem:
                if cancel.is_set():
                    r = {"ok": False, "state": "cancelled",
                         "error_code": "cancelled", "error": "cancelled",
                         "detail": "已取消", "reachable": False,
                         "latency_ms": None, "status": 0, "models": []}
                else:
                    try:
                        async with make_client(settings) as client:
                            r = await tester.test_connectivity(
                                client, p, get_protocol(p.protocol), settings)
                    except Exception as exc:
                        r = tester.failure_from_exception(
                            exc, float(settings.get("timeout_s", 10)), p.api_key)
            results.append(r)
            self.conn_result.emit(p.id, r)

        try:
            await asyncio.gather(*(one(p) for p in providers),
                                 return_exceptions=True)
        finally:
            self._end_batch_summary(results, "连通")

    def test_provider_ttft(self, provider) -> bool:
        if self.batch_running or self.is_provider_busy(provider.id):
            return False
        if not provider.models:
            return False
        self._begin_batch()
        self._provider_busy.add(provider.id)
        self._batch_future = self.submit(self._ttft_batch(provider))
        return True

    async def _ttft_batch(self, provider):
        settings = self._get_settings()
        sem = asyncio.Semaphore(int(settings.get("concurrency", 3)))
        models = [m.id for m in provider.models]
        total = len(models)
        done = fails = 0
        cancel = self._cancel_evt

        async def one(mid):
            nonlocal done, fails
            if cancel.is_set():
                return
            async with sem:
                if cancel.is_set():
                    return
                try:
                    async with make_client(settings) as client:
                        r = await tester.run_ttft(
                            client, provider,
                            get_protocol(provider.protocol),
                            mid, settings, cancel.is_set)
                except Exception as exc:
                    r = tester.failure_from_exception(
                        exc, float(settings.get("timeout_s", 10)), provider.api_key,
                        tester.effective_max_tokens(settings))
            if cancel.is_set():
                return
            if not r.get("ok"):
                fails += 1
            done += 1
            self.ttft_result.emit(provider.id, mid, r)
            self.ttft_progress.emit(provider.id, done, total, fails)

        try:
            await asyncio.gather(*(one(m) for m in models),
                                 return_exceptions=True)
        finally:
            self._provider_busy.discard(provider.id)
            if cancel.is_set():
                summary = f"首字批量已取消：完成 {done}/{total}（失败 {fails}）"
            else:
                summary = f"首字批量完成：成功 {total - fails} · 失败 {fails}"
            self.batch_finished.emit(summary)
            self._finish_batch()

    # ---- 批量状态 ----
    def _begin_batch(self):
        self.batch_running = True
        self._cancel_evt = asyncio.Event()
        self._batch_future = None
        self.batch_changed.emit()

    def _finish_batch(self):
        self.batch_running = False
        self._cancel_evt = None
        self._batch_future = None
        self.batch_changed.emit()

    def _end_batch_summary(self, results, kind):
        if self._cancel_evt is not None and self._cancel_evt.is_set():
            self.batch_finished.emit(f"{kind}批量已取消")
        else:
            oks = [r for r in results if r.get("ok")]
            if oks:
                avg = round(sum(r["latency_ms"] for r in oks) / len(oks))
                self.batch_finished.emit(
                    f"{kind}批量完成：成功 {len(oks)} · 失败 {len(results) - len(oks)}"
                    f" · 平均 {avg}ms")
            else:
                self.batch_finished.emit(
                    f"{kind}批量完成：成功 0 · 失败 {len(results)}")
        self._finish_batch()

    def cancel_current(self):
        if self._cancel_evt is not None and self.loop is not None:
            self.loop.call_soon_threadsafe(self._cancel_evt.set)
            if self._batch_future is not None:
                self.loop.call_soon_threadsafe(self._batch_future.cancel)
