import argparse

import mangapy.cli as cli
from mangapy import download_manager


def _capture_request(monkeypatch):
    captured = {}

    def fake_download(self, request):
        captured["request"] = request

    monkeypatch.setattr(cli.DownloadManager, "download", fake_download)
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
    captured = _capture_request(monkeypatch)
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

    assert captured["request"].proxy == {"http": "h", "https": "s"}


def test_main_title_rejects_proxy_missing_http(monkeypatch):
    captured = _capture_request(monkeypatch)
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

    assert captured["request"].proxy is None


def test_download_range_allows_zero_start():
    assert download_manager._parse_range("0-2") == (0.0, 2.0)
