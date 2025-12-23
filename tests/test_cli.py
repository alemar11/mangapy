import argparse

import mangapy.cli as cli


def _capture_download(monkeypatch):
    captured = {}

    def fake_start(download):
        captured["download"] = download

    monkeypatch.setattr(cli, "start_download", fake_start)
    return captured


def test_cmd_parse_title(monkeypatch):
    argv = [
        "mangapy",
        "title",
        "bleach",
        "-a",
        "--pdf",
        "-o",
        "/tmp/out",
        "-p",
        '{"http": "h", "https": "s"}',
    ]
    monkeypatch.setattr(cli.sys, "argv", argv)
    args = cli.cmd_parse()

    assert args.mode == "title"
    assert args.manga_title == "bleach"
    assert args.all is True
    assert args.pdf is True
    assert args.out == "/tmp/out"
    assert args.proxy == {"http": "h", "https": "s"}


def test_main_title_accepts_valid_proxy(monkeypatch):
    captured = _capture_download(monkeypatch)
    args = argparse.Namespace(
        manga_title="bleach",
        out="/tmp/out",
        pdf=False,
        source=None,
        debug=False,
        proxy={"http": "h", "https": "s"},
        all=False,
        chapter=None,
    )

    cli.main_title(args)

    assert captured["download"].proxy == {"http": "h", "https": "s"}


def test_main_title_rejects_proxy_missing_http(monkeypatch):
    captured = _capture_download(monkeypatch)
    args = argparse.Namespace(
        manga_title="bleach",
        out="/tmp/out",
        pdf=False,
        source=None,
        debug=False,
        proxy={"https": "s"},
        all=False,
        chapter=None,
    )

    cli.main_title(args)

    assert captured["download"].proxy is None
