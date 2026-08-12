from __future__ import annotations

import logging
import threading
from collections.abc import Iterable
from typing import Literal

from rich.console import Console, RenderableType
from rich.logging import RichHandler
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    Task,
    TaskID,
    TextColumn,
    TimeRemainingColumn,
)
from rich.table import Table
from rich.text import Text
from rich.theme import Theme

MessageKind = Literal["info", "success", "warning", "error", "muted"]

_THEME = Theme(
    {
        "mangapy.info": "bold cyan",
        "mangapy.success": "bold green",
        "mangapy.warning": "bold yellow",
        "mangapy.error": "bold red",
        "mangapy.muted": "dim",
    }
)
_DEFAULT_ICONS: dict[MessageKind, str] = {
    "info": "●",
    "success": "✓",
    "warning": "!",
    "error": "✕",
    "muted": "•",
}

stdout = Console(theme=_THEME, markup=False, highlight=False)
stderr = Console(theme=_THEME, markup=False, highlight=False, stderr=True)
_managed_logging_handler: RichHandler | None = None

_PROVIDER_LABELS = {
    "fanfox": "FanFox",
    "mangadex": "MangaDex",
}


class _DeterminateBarColumn(BarColumn):
    def render(self, task: Task) -> RenderableType:
        if task.total is None:
            return Text()
        return super().render(task)


class _DeterminateMofNColumn(MofNCompleteColumn):
    def render(self, task: Task) -> Text:
        if task.total is None:
            return Text()
        return super().render(task)


class _DeterminateTimeRemainingColumn(TimeRemainingColumn):
    def render(self, task: Task) -> Text:
        if task.total is None:
            return Text()
        return super().render(task)


class _ProgressDisplay:
    def __init__(self, console: Console):
        self.console = console
        self.progress = Progress(
            SpinnerColumn(style="mangapy.info"),
            TextColumn("{task.description}", style="mangapy.info", markup=False),
            _DeterminateBarColumn(bar_width=24),
            _DeterminateMofNColumn(),
            TextColumn("{task.fields[unit]}", markup=False),
            _DeterminateTimeRemainingColumn(compact=True),
            console=console,
            transient=True,
            redirect_stdout=False,
            redirect_stderr=False,
        )
        self._lifecycle_lock = threading.Lock()
        self._context_depth = 0

    def acquire(self) -> None:
        with self._lifecycle_lock:
            if self._context_depth == 0:
                self.progress.start()
            self._context_depth += 1

    def release(self) -> None:
        with self._lifecycle_lock:
            self._context_depth -= 1
            if self._context_depth == 0:
                self.progress.stop()


_shared_progress_lock = threading.Lock()
_shared_progress_display: _ProgressDisplay | None = None


def _get_shared_progress_display() -> _ProgressDisplay:
    global _shared_progress_display
    with _shared_progress_lock:
        if _shared_progress_display is None:
            _shared_progress_display = _ProgressDisplay(stderr)
        return _shared_progress_display


class DownloadProgress:
    def __init__(self, enabled: bool = True, *, console: Console | None = None):
        self._requested_enabled = enabled
        self._display = _ProgressDisplay(console) if console is not None else _get_shared_progress_display()
        self._progress = self._display.progress
        self._context_local = threading.local()
        self._lifecycle_lock = threading.Lock()
        self._active_contexts = 0
        self._session_task_id: TaskID | None = None

    @property
    def enabled(self) -> bool:
        states = getattr(self._context_local, "states", ())
        if states:
            return states[-1]
        return self._requested_enabled and self._display.console.is_terminal

    def __enter__(self) -> DownloadProgress:
        active = self._requested_enabled and self._display.console.is_terminal
        if active:
            self._display.acquire()
            with self._lifecycle_lock:
                self._active_contexts += 1
        states = getattr(self._context_local, "states", None)
        if states is None:
            states = []
            self._context_local.states = states
        states.append(active)
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        active = self._context_local.states.pop()
        if active:
            session_task_id = None
            with self._lifecycle_lock:
                self._active_contexts -= 1
                if self._active_contexts == 0:
                    session_task_id = self._session_task_id
                    self._session_task_id = None
            if session_task_id is not None:
                self._progress.remove_task(session_task_id)
            self._display.release()

    def start_search(self, title: str, source: str) -> None:
        if not self.enabled:
            return
        description = f"Searching · {title} · {provider_label(source)}"
        with self._lifecycle_lock:
            if self._session_task_id is None:
                self._session_task_id = self._progress.add_task(description, total=None, unit="")
            else:
                self._progress.update(self._session_task_id, description=description, total=None, completed=0, unit="")

    def start_download(self, title: str, source: str, total_chapters: int) -> None:
        if not self.enabled:
            return
        description = f"{title} · {provider_label(source)}"
        with self._lifecycle_lock:
            if self._session_task_id is None:
                self._session_task_id = self._progress.add_task(
                    description,
                    total=total_chapters,
                    unit="chapters",
                )
            else:
                self._progress.update(
                    self._session_task_id,
                    description=description,
                    total=total_chapters,
                    completed=0,
                    unit="chapters",
                )

    def advance_download(self) -> None:
        with self._lifecycle_lock:
            task_id = self._session_task_id
        if task_id is not None:
            self._progress.advance(task_id)

    def clear_session(self) -> None:
        with self._lifecycle_lock:
            task_id = self._session_task_id
            self._session_task_id = None
        if task_id is not None:
            self._progress.remove_task(task_id)
            self._progress.refresh()

    def add_chapter(self, chapter_name: str, total_pages: int) -> TaskID | None:
        if not self.enabled:
            return None
        return self._progress.add_task(f"  Chapter {chapter_name}", total=total_pages, unit="pages")

    def advance(self, task_id: TaskID | None) -> None:
        if task_id is not None:
            self._progress.advance(task_id)

    def remove_chapter(self, task_id: TaskID | None) -> None:
        if task_id is not None:
            self._progress.remove_task(task_id)


def info(message: object, *, icon: str | None = None) -> None:
    _write(message, kind="info", icon=icon)


def success(message: object, *, icon: str | None = None) -> None:
    _write(message, kind="success", icon=icon)


def warning(message: object, *, icon: str | None = None, to_stderr: bool = True) -> None:
    _write(message, kind="warning", icon=icon, to_stderr=to_stderr)


def error(message: object, *, icon: str | None = None, to_stderr: bool = True) -> None:
    _write(message, kind="error", icon=icon, to_stderr=to_stderr)


def muted(message: object, *, icon: str | None = None) -> None:
    _write(message, kind="muted", icon=icon)


def suggestions(values: Iterable[object]) -> None:
    info("Did you mean one of these?", icon="?")
    table = Table.grid(padding=(0, 1))
    for value in values:
        table.add_row(Text("•", style="mangapy.info"), Text(str(value)))
    stdout.print(table, soft_wrap=True)


def configure_logging(debug: bool) -> None:
    global _managed_logging_handler

    level = logging.DEBUG if debug else logging.ERROR
    root_logger = logging.getLogger()
    mangapy_logger = logging.getLogger("mangapy")
    if _managed_logging_handler in root_logger.handlers:
        root_logger.setLevel(level)
    elif not root_logger.handlers and not mangapy_logger.handlers:
        handler = RichHandler(
            console=stderr,
            show_time=False,
            show_path=False,
            enable_link_path=False,
            markup=False,
            rich_tracebacks=True,
            tracebacks_show_locals=False,
        )
        handler.setFormatter(logging.Formatter("%(message)s"))
        root_logger.addHandler(handler)
        root_logger.setLevel(level)
        _managed_logging_handler = handler
    mangapy_logger.setLevel(level)


def _write(
    message: object,
    *,
    kind: MessageKind,
    icon: str | None,
    to_stderr: bool = False,
) -> None:
    output = stderr if to_stderr else stdout
    output.print(_message_text(message, kind=kind, icon=icon), soft_wrap=True)


def _message_text(message: object, *, kind: MessageKind, icon: str | None = None) -> Text:
    text = Text()
    text.append(icon or _DEFAULT_ICONS[kind], style=f"mangapy.{kind}")
    text.append("  ")
    text.append(str(message))
    return text


def provider_label(source: str) -> str:
    return _PROVIDER_LABELS.get(source.casefold(), source)
