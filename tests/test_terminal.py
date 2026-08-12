import logging
from io import StringIO
from threading import Thread
from unittest.mock import Mock

import pytest
from rich.console import Console
from rich.logging import RichHandler

from mangapy import terminal


def test_terminal_messages_preserve_literal_text_and_streams(capsys):
    terminal.info("Provider [broken]")
    terminal.error("Failure [not markup]")

    captured = capsys.readouterr()
    assert "Provider [broken]" in captured.out
    assert "Failure [not markup]" in captured.err
    assert "\x1b" not in captured.out
    assert "\x1b" not in captured.err


def test_suggestions_are_rendered_on_stdout(capsys):
    terminal.suggestions(["One Piece", "Title [literal]"])

    captured = capsys.readouterr()
    assert "Did you mean one of these?" in captured.out
    assert "One Piece" in captured.out
    assert "Title [literal]" in captured.out
    assert captured.err == ""


def test_configure_logging_installs_one_rich_stderr_handler(capsys):
    root_logger = logging.getLogger()
    mangapy_logger = logging.getLogger("mangapy")
    original_handlers = list(root_logger.handlers)
    original_root_level = root_logger.level
    original_mangapy_level = mangapy_logger.level
    installed_handlers = []

    try:
        root_logger.handlers = []
        terminal.configure_logging(debug=False)
        terminal.configure_logging(debug=True)
        installed_handlers = list(root_logger.handlers)

        assert len(installed_handlers) == 1
        assert isinstance(installed_handlers[0], RichHandler)
        assert installed_handlers[0].console.stderr
        assert installed_handlers[0].markup is False

        logging.getLogger("mangapy.test").debug("Debug [literal]")
        captured = capsys.readouterr()
        assert captured.err.count("Debug [literal]") == 1
        assert "\x1b" not in captured.err
    finally:
        root_logger.handlers = original_handlers
        root_logger.setLevel(original_root_level)
        mangapy_logger.setLevel(original_mangapy_level)
        for handler in installed_handlers:
            handler.close()


def test_configure_logging_disables_debug_again_for_loggers_using_managed_root(capsys):
    root_logger = logging.getLogger()
    mangapy_logger = logging.getLogger("mangapy")
    third_party_logger = logging.getLogger("third_party_test")
    original_handlers = list(root_logger.handlers)
    original_root_level = root_logger.level
    original_mangapy_level = mangapy_logger.level
    original_third_party_level = third_party_logger.level
    original_third_party_propagate = third_party_logger.propagate
    installed_handlers = []

    try:
        root_logger.handlers = []
        third_party_logger.setLevel(logging.NOTSET)
        third_party_logger.propagate = True

        terminal.configure_logging(debug=True)
        third_party_logger.debug("Visible third-party debug")
        assert "Visible third-party debug" in capsys.readouterr().err

        terminal.configure_logging(debug=False)
        assert root_logger.level == logging.ERROR
        assert mangapy_logger.level == logging.ERROR

        third_party_logger.debug("Hidden third-party debug")
        assert "Hidden third-party debug" not in capsys.readouterr().err
        installed_handlers = list(root_logger.handlers)
    finally:
        root_logger.handlers = original_handlers
        root_logger.setLevel(original_root_level)
        mangapy_logger.setLevel(original_mangapy_level)
        third_party_logger.setLevel(original_third_party_level)
        third_party_logger.propagate = original_third_party_propagate
        for handler in installed_handlers:
            handler.close()


def test_configure_logging_preserves_an_existing_root_handler():
    root_logger = logging.getLogger()
    mangapy_logger = logging.getLogger("mangapy")
    original_handlers = list(root_logger.handlers)
    original_root_level = root_logger.level
    original_mangapy_level = mangapy_logger.level
    existing_handler = logging.StreamHandler(StringIO())

    try:
        root_logger.handlers = [existing_handler]
        root_logger.setLevel(logging.WARNING)
        terminal.configure_logging(debug=True)

        assert root_logger.handlers == [existing_handler]
        assert root_logger.level == logging.WARNING

        terminal.configure_logging(debug=False)

        assert root_logger.handlers == [existing_handler]
        assert root_logger.level == logging.WARNING
    finally:
        root_logger.handlers = original_handlers
        root_logger.setLevel(original_root_level)
        mangapy_logger.setLevel(original_mangapy_level)
        existing_handler.close()


def test_download_progress_is_disabled_without_a_terminal():
    output = StringIO()
    progress = terminal.DownloadProgress(console=Console(file=output, force_terminal=False))

    with progress:
        task_id = progress.add_chapter("1", 1)
        progress.advance(task_id)
        progress.remove_chapter(task_id)

    assert not progress.enabled
    assert output.getvalue() == ""


def test_download_progress_flag_disables_a_terminal():
    output = StringIO()
    progress = terminal.DownloadProgress(
        enabled=False,
        console=Console(file=output, force_terminal=True, theme=terminal._THEME),
    )

    with progress:
        task_id = progress.add_chapter("1", 1)
        progress.advance(task_id)
        progress.remove_chapter(task_id)

    assert not progress.enabled
    assert output.getvalue() == ""


def test_download_progress_uses_one_reentrant_lifecycle():
    progress = terminal.DownloadProgress(console=Console(file=StringIO(), force_terminal=True, theme=terminal._THEME))
    start = Mock(wraps=progress._progress.start)
    stop = Mock(wraps=progress._progress.stop)
    progress._progress.start = start
    progress._progress.stop = stop

    with progress:
        with progress:
            task_id = progress.add_chapter("1", 1)
            progress.advance(task_id)
            progress.remove_chapter(task_id)

    assert progress.enabled
    assert start.call_count == 1
    assert stop.call_count == 1


def test_download_progress_stops_after_an_exception():
    progress = terminal.DownloadProgress(console=Console(file=StringIO(), force_terminal=True, theme=terminal._THEME))
    stop = Mock(wraps=progress._progress.stop)
    progress._progress.stop = stop

    with pytest.raises(RuntimeError, match="worker failed"):
        with progress:
            raise RuntimeError("worker failed")

    assert stop.call_count == 1
    assert progress._display._context_depth == 0


def test_download_progress_preserves_literal_chapter_names():
    output = StringIO()
    console = Console(file=output, force_terminal=True, color_system=None, theme=terminal._THEME)
    progress = terminal.DownloadProgress(console=console)
    progress.add_chapter("[red]literal[/red]", 2)

    console.print(progress._progress.get_renderable())

    assert "Chapter [red]literal[/red]" in output.getvalue()


def test_download_progress_transitions_from_search_to_download_summary():
    output = StringIO()
    progress = terminal.DownloadProgress(
        console=Console(file=output, force_terminal=True, color_system=None, theme=terminal._THEME)
    )

    with progress:
        progress.start_search("Bleach", "fanfox")
        session_task = progress._progress.tasks[0]
        assert session_task.description == "Searching · Bleach · FanFox"
        assert session_task.total is None
        assert session_task.fields["unit"] == ""
        search_renderable = progress._progress.get_renderable()
        search_output = StringIO()
        Console(file=search_output, force_terminal=False, width=100).print(search_renderable)
        assert "0/?" not in search_output.getvalue()

        progress.start_download("Bleach", "fanfox", 2)
        progress.advance_download()

        session_task = progress._progress.tasks[0]
        assert session_task.description == "Bleach · FanFox"
        assert session_task.total == 2
        assert session_task.completed == 1
        assert session_task.fields["unit"] == "chapters"

    assert progress._progress.tasks == []


def test_download_session_survives_a_nested_worker_context():
    progress = terminal.DownloadProgress(
        console=Console(file=StringIO(), force_terminal=True, color_system=None, theme=terminal._THEME)
    )

    with progress:
        progress.start_search("Bleach", "fanfox")

        worker = Thread(target=lambda: _enter_progress_once(progress))
        worker.start()
        worker.join(timeout=2)

        assert not worker.is_alive()
        assert len(progress._progress.tasks) == 1

    assert progress._progress.tasks == []


def test_download_progress_can_clear_search_before_an_error_message():
    progress = terminal.DownloadProgress(
        console=Console(file=StringIO(), force_terminal=True, color_system=None, theme=terminal._THEME)
    )

    with progress:
        progress.start_search("Missing", "fanfox")
        progress.clear_session()

        assert progress._progress.tasks == []


def _enter_progress_once(progress):
    with progress:
        pass


def test_download_progress_instances_share_one_global_lifecycle(monkeypatch):
    console = Console(file=StringIO(), force_terminal=True, theme=terminal._THEME)
    monkeypatch.setattr(terminal, "stderr", console)
    monkeypatch.setattr(terminal, "_shared_progress_display", None)
    first = terminal.DownloadProgress()
    second = terminal.DownloadProgress()
    start = Mock(wraps=first._progress.start)
    stop = Mock(wraps=first._progress.stop)
    first._progress.start = start
    first._progress.stop = stop

    first.__enter__()
    second.__enter__()
    first.__exit__(None, None, None)

    assert first._progress is second._progress
    assert start.call_count == 1
    assert stop.call_count == 0
    assert first._display._context_depth == 1
    assert first._progress.live.is_started

    second.__exit__(None, None, None)

    assert stop.call_count == 1
    assert first._display._context_depth == 0
    assert not first._progress.live.is_started


def test_download_progress_rechecks_terminal_state_when_used():
    class MutableTerminal(StringIO):
        is_terminal = False

        def isatty(self):
            return self.is_terminal

    output = MutableTerminal()
    progress = terminal.DownloadProgress(console=Console(file=output))

    assert not progress.enabled
    output.is_terminal = True
    assert progress.enabled
    output.is_terminal = False
    assert not progress.enabled
