from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Literal

from rich.console import Console
from rich.logging import RichHandler
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
