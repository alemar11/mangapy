import logging
from io import StringIO

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


def test_configure_logging_preserves_an_existing_root_handler():
    root_logger = logging.getLogger()
    mangapy_logger = logging.getLogger("mangapy")
    original_handlers = list(root_logger.handlers)
    original_root_level = root_logger.level
    original_mangapy_level = mangapy_logger.level
    existing_handler = logging.StreamHandler(StringIO())

    try:
        root_logger.handlers = [existing_handler]
        terminal.configure_logging(debug=False)

        assert root_logger.handlers == [existing_handler]
    finally:
        root_logger.handlers = original_handlers
        root_logger.setLevel(original_root_level)
        mangapy_logger.setLevel(original_mangapy_level)
        existing_handler.close()
