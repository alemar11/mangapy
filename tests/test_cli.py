import argparse

import yaml

import mangapy.cli as cli
from mangapy import download_manager


def _capture_request(monkeypatch):
    captured = {}

    def fake_download(self, request):
        captured["request"] = request

    monkeypatch.setattr(cli.DownloadManager, "download", fake_download)
    return captured


def _capture_requests(monkeypatch):
    captured = []

    def fake_download(self, request):
        captured.append(request)

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


def test_cmd_parse_yaml(monkeypatch, tmp_path):
    yaml_path = tmp_path / "sample.yaml"
    yaml_path.write_text("downloads: []")
    monkeypatch.setattr(cli.sys, "argv", ["mangapy", "yaml", str(yaml_path)])
    args = cli.cmd_parse()

    assert args.mode == "yaml"
    assert args.yaml_file == str(yaml_path)


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


def test_main_title_source_and_range(monkeypatch):
    captured = _capture_request(monkeypatch)
    args = argparse.Namespace(
        manga_title="bleach",
        out="/tmp/out",
        pdf=True,
        source="MangaDex",
        debug=True,
        proxy=None,
        all=False,
        chapter="1-3",
    )

    cli.main_title(args)

    request = captured["request"]
    assert request.source == "mangadex"
    assert request.pdf is True
    assert request.enable_debug_log is True
    assert request.download_single_chapter is None
    assert request.download_chapters == "1-3"


def test_download_range_allows_zero_start():
    assert download_manager._parse_range("0-2") == (0.0, 2.0)


def test_normalize_source():
    assert cli._normalize_source(" MangaDex ") == "mangadex"


def test_parse_single_chapter_and_range():
    assert cli._parse_single_chapter("3") == "3"
    assert cli._parse_single_chapter("1-2") is None
    assert cli._parse_chapter_range("1-2") == "1-2"
    assert cli._parse_chapter_range("1") is None


def test_extract_options():
    assert cli._extract_options({"title": "x"}) is None
    options = cli._extract_options(
        {"translated_language": ["it"], "content_rating": "safe", "data_saver": True}
    )
    assert options == {"translated_language": ["it"], "content_rating": "safe", "data_saver": True}


def test_normalize_yaml_downloads_legacy_structure():
    dictionary = {
        "output": "/tmp/out",
        "fanfox": [{"title": "Bleach"}],
        "mangadex": [{"title": "One Piece"}],
    }
    downloads = cli._normalize_yaml_downloads(dictionary)
    assert len(downloads) == 2
    assert downloads[0]["source"] in {"fanfox", "mangadex"}
    sources = {entry["source"] for entry in downloads}
    assert sources == {"fanfox", "mangadex"}


def test_main_yaml_downloads_list(monkeypatch, tmp_path):
    captured = _capture_requests(monkeypatch)
    yaml_path = tmp_path / "sample.yaml"
    payload = {
        "output": "/tmp/root",
        "debug": True,
        "proxy": {"http": "h", "https": "s"},
        "downloads": [
            {
                "title": "Bleach",
                "source": "Mangadex",
                "download_all_chapters": True,
                "translated_language": ["it"],
                "content_rating": "safe",
                "data_saver": True,
            },
            {"title": ""},
            {
                "title": "Naruto",
                "source": "fanfox",
                "output": "/tmp/override",
                "proxy": {"http": "h2", "https": "s2"},
                "download_single_chapter": "5",
            },
        ],
    }
    yaml_path.write_text(yaml.dump(payload))
    args = argparse.Namespace(yaml_file=str(yaml_path))

    cli.main_yaml(args)

    assert len(captured) == 2
    first, second = captured
    assert first.title == "Bleach"
    assert first.source == "mangadex"
    assert first.output == "/tmp/root"
    assert first.proxy == {"http": "h", "https": "s"}
    assert first.download_all_chapters is True
    assert first.options == {
        "translated_language": ["it"],
        "content_rating": "safe",
        "data_saver": True,
    }

    assert second.title == "Naruto"
    assert second.source == "fanfox"
    assert second.output == "/tmp/override"
    assert second.proxy == {"http": "h2", "https": "s2"}
    assert second.download_single_chapter == "5"
