"""轻量进度显示：纯标准库实现，无第三方依赖。

设计要点
--------
- **不引入 tqdm**：项目整体取向是"只依赖 numpy/pandas/scipy/matplotlib/openpyxl"，
  这里用标准库自实现，避免为一个进度条增加依赖。
- **自适应输出**：终端下用 ``\\r`` 原地刷新；输出被重定向到文件时自动改为按百分比
  打点，避免把日志刷成几万行。
- **自适应编码**：终端不支持 Unicode 时自动降级为纯 ASCII 进度条，不会因编码抛异常。
- **可关闭**：环境变量 ``GREENOPT_PROGRESS=0`` 或命令行 ``--no-progress``。

用法
----
    from greenopt.progress import ProgressBar, step

    bar = ProgressBar(total=100, desc="PSO", unit=" 次评价")
    for i in range(100):
        bar.update(1, 最优="1.23e7")
    bar.close()

    with step("构建场景", 2, 8):
        ...
"""
from __future__ import annotations

import os
import shutil
import sys
import time
import unicodedata
from contextlib import contextmanager

__all__ = ["ProgressBar", "step", "enabled", "set_enabled", "fmt_duration"]

_ENABLED: bool | None = None


# ------------------------------------------------------------------ 开关
def enabled() -> bool:
    """是否启用进度输出；读取环境变量 GREENOPT_PROGRESS，默认开启。"""
    global _ENABLED
    if _ENABLED is None:
        raw = os.environ.get("GREENOPT_PROGRESS", "1").strip().lower()
        _ENABLED = raw not in {"0", "false", "off", "no", "none", ""}
    return _ENABLED


def set_enabled(flag: bool) -> None:
    global _ENABLED
    _ENABLED = bool(flag)


def _is_tty() -> bool:
    try:
        return bool(sys.stdout.isatty())
    except Exception:
        return False


# ------------------------------------------------------------------ 输出
def _write(text: str) -> None:
    """写 stdout，编码不支持时降级为 ASCII，避免半路抛 UnicodeEncodeError。"""
    try:
        sys.stdout.write(text)
    except UnicodeEncodeError:
        sys.stdout.write(text.encode("ascii", "replace").decode("ascii"))
    try:
        sys.stdout.flush()
    except Exception:
        pass


def _width(text: str) -> int:
    """显示宽度：中日韩全角字符按 2 列计，用于行尾补空格清除残留。"""
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in text)


def _fit(text: str, limit: int) -> str:
    """按显示宽度截断，避免中文占两列导致超出终端宽度。"""
    if _width(text) <= limit:
        return text
    out, used = [], 0
    for ch in text:
        cw = 2 if unicodedata.east_asian_width(ch) in "WF" else 1
        if used + cw > limit:
            break
        out.append(ch)
        used += cw
    return "".join(out)


def fmt_duration(seconds: float | None) -> str:
    """把秒格式化成 m:ss 或 h:mm:ss。"""
    if seconds is None or seconds != seconds or seconds < 0:
        return "--:--"
    total = int(round(seconds))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


# ------------------------------------------------------------------ 进度条
class ProgressBar:
    """带 ETA 的进度条。

    参数
    ----
    total : int | None
        总步数；``None`` 表示不确定总数，只显示已完成计数。
    desc : str
        进度条前缀说明。
    unit : str
        计数单位后缀，如 ``" 次评价"``。
    fields
        每次 update 可传额外键值，拼在行尾（如 代数 / 最优值）。
    """

    def __init__(self, total: int | None = None, desc: str = "",
                 width: int = 18, unit: str = "",
                 min_interval: float = 0.12, log_every_pct: float = 10.0):
        self.total = total
        self.done = 0
        self.desc = desc
        self.width = max(6, int(width))
        self.unit = unit
        self.min_interval = min_interval
        self.log_every_pct = log_every_pct
        self.start = time.perf_counter()
        self._last_tick = 0.0
        self._max_width = 0
        self._last_pct = -1.0
        self._fields: dict[str, str] = {}
        self._closed = False
        try:
            self._cols = shutil.get_terminal_size((100, 24)).columns
        except Exception:
            self._cols = 100

    # -- 内部计算 --------------------------------------------------
    def _elapsed(self) -> float:
        return time.perf_counter() - self.start

    def _eta(self) -> float | None:
        if not self.total or self.done <= 0:
            return None
        rate = self.done / max(self._elapsed(), 1e-9)
        return max(0.0, (self.total - self.done) / rate) if rate > 0 else None

    def _render(self) -> str:
        """生成一行进度文本；超宽时依次丢弃附加字段、缩短进度条、截断描述，
        确保永不折行（折行会让 \\r 原地刷新失效）。"""
        limit = max(20, self._cols - 1)
        desc, bar_w = self.desc, self.width
        fields = "".join(f"  {k}={v}" for k, v in self._fields.items())
        show_tail = True
        while True:
            if self.total:
                frac = min(1.0, self.done / max(self.total, 1))
                filled = int(round(bar_w * frac))
                bar = "=" * filled + "-" * (bar_w - filled)
                head = f"{desc} [{bar}] {frac * 100:5.1f}%  {self.done}/{self.total}{self.unit}"
                tail = f"  ETA {fmt_duration(self._eta())}" if show_tail else ""
            else:
                head = f"{desc} [~~~~~~~~] 已 {self.done}{self.unit}"
                tail = ""
            text = f"{head}  已用 {fmt_duration(self._elapsed())}{tail}{fields}"
            if _width(text) <= limit:
                return text
            # 逐级降级：字段 -> 进度条 -> ETA -> 描述 -> 硬截断
            if fields:
                fields = ""
            elif bar_w > 8:
                bar_w -= 2
            elif show_tail:
                show_tail = False
            elif len(desc) > 6:
                desc = desc[:-2]
            else:
                return _fit(text, limit)

    def _emit(self, final: bool = False) -> None:
        text = self._render()
        if _is_tty():
            pad = max(0, self._max_width - _width(text))
            _write("\r" + text + " " * pad)
            self._max_width = max(self._max_width, _width(text))
        else:
            if final:
                _write(text + "\n")
            elif self.total:
                pct = 100.0 * self.done / max(self.total, 1)
                if pct - self._last_pct >= self.log_every_pct:
                    self._last_pct = pct
                    _write(text + "\n")
            elif self.done and self.done % 50 == 0:
                _write(text + "\n")

    # -- 对外接口 --------------------------------------------------
    def update(self, n: int = 1, **fields: str) -> None:
        """推进 n 步；fields 为附加显示字段。"""
        self.done += n
        if fields:
            self._fields.update({k: str(v) for k, v in fields.items()})
        if not enabled() or self._closed:
            return
        finished = bool(self.total) and self.done >= self.total
        now = self._elapsed()
        # 节流：非末尾步且距上次刷新太近就跳过，避免刷屏拖慢求解
        if _is_tty() and not finished and (now - self._last_tick) < self.min_interval:
            return
        self._last_tick = now
        self._emit(final=finished)

    def close(self) -> None:
        """结束进度条所在行。"""
        if self._closed:
            return
        self._closed = True
        if not enabled():
            return
        if _is_tty():
            self._emit(final=True)
            _write("\n")
        else:
            if not (self.total and self.done >= self.total):
                self._emit(final=True)

    # 便于 with 语句使用
    def __enter__(self) -> "ProgressBar":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


# ------------------------------------------------------------------ 阶段行
@contextmanager
def step(name: str, index: int | None = None, total: int | None = None):
    """打印阶段标题，结束时补上耗时。

    >>> with step("构建调度场景", 2, 8):
    ...     pass
    [2/8] 构建调度场景
          -> 完成，耗时 0:01
    """
    if not enabled():
        yield
        return
    prefix = f"[{index}/{total}] " if index and total else ""
    indent = " " * (len(prefix) + 2)
    _write(f"{prefix}{name}\n")
    start = time.perf_counter()
    try:
        yield
    except BaseException:
        _write(f"{indent}-> 中断，耗时 {fmt_duration(time.perf_counter() - start)}\n")
        raise
    elapsed = time.perf_counter() - start
    if elapsed >= 0.2:      # 极快的阶段不补行，避免刷屏
        _write(f"{indent}-> 完成，耗时 {fmt_duration(elapsed)}\n")
