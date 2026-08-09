import argparse

import pytest
import yaml

import mangapy.cli as cli
from mangapy import download_manager
from mangapy.download_manager import DownloadResult


def _capture_request(monkeypatch):
    captured = {}

    def fake_download(self, request):
        captured["request"] = request
        return DownloadResult(selected_chapters=1, downloaded_chapters=1)

    monkeypatch.setattr(cli.DownloadManager, "download", fake_download)
    return captured


def _capture_requests(monkeypatch):
    captured = []

    def fake_download(self, request):
        captured.append(request)
        return DownloadResult(selected_chapters=1, downloaded_chapters=1)

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
        '{"http": "http://proxy.example:8080", "https": "http://proxy.example:8080"}',
    ]
    monkeypatch.setattr(cli.sys, "argv", argv)
    args = cli.cmd_parse()

    assert args.mode == "title"
    assert args.manga_title == "bleach"
    assert args.all is True
    assert args.pdf is True
    assert args.out == "/tmp/out"
    assert args.proxy == {"http": "http://proxy.example:8080", "https": "http://proxy.example:8080"}


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
        proxy={"http": "http://proxy.example:8080", "https": "http://proxy.example:8080"},
        all=False,
        chapter=None,
        no_progress=False,
    )

    exit_code = cli.main_title(args)

    assert exit_code == 0
    assert captured["request"].proxy == {
        "http": "http://proxy.example:8080",
        "https": "http://proxy.example:8080",
    }


def test_main_title_rejects_proxy_missing_http(monkeypatch):
    captured = _capture_request(monkeypatch)
    args = argparse.Namespace(
        manga_title="bleach",
        out="/tmp/out",
        pdf=False,
        source=None,
        debug=False,
        proxy={"https": "http://proxy.example:8080"},
        all=False,
        chapter=None,
        no_progress=False,
    )

    exit_code = cli.main_title(args)

    assert exit_code == 1
    assert "request" not in captured


def test_main_title_rejects_empty_proxy_mapping(monkeypatch):
    captured = _capture_request(monkeypatch)
    args = argparse.Namespace(
        manga_title="bleach",
        out="/tmp/out",
        pdf=False,
        source=None,
        debug=False,
        proxy={},
        all=False,
        chapter=None,
        no_progress=False,
    )

    exit_code = cli.main_title(args)

    assert exit_code == 1
    assert "request" not in captured


@pytest.mark.parametrize(
    "proxy_url",
    ["http://:8080", "http://host:bad", "http://[", "http://host:99999", "http://proxy example"],
)
def test_proxy_validation_rejects_malformed_urls(proxy_url):
    proxy = {"http": proxy_url, "https": proxy_url}

    assert not cli._is_valid_proxy(proxy)


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
        no_progress=False,
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
    options = cli._extract_options({"translated_language": ["it"], "content_rating": "safe", "data_saver": True})
    assert options == {"translated_language": ["it"], "content_rating": ["safe"], "data_saver": True}


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


def test_normalize_yaml_downloads_keeps_legacy_provider_groups_case_insensitive():
    downloads = cli._normalize_yaml_downloads({"FanFox": [{"title": "Bleach"}]})

    assert downloads == [{"title": "Bleach", "source": "fanfox"}]


def test_main_yaml_downloads_list(monkeypatch, tmp_path):
    captured = _capture_requests(monkeypatch)
    yaml_path = tmp_path / "sample.yaml"
    payload = {
        "output": "/tmp/root",
        "debug": True,
        "proxy": {"http": "http://proxy.example:8080", "https": "http://proxy.example:8080"},
        "downloads": [
            {
                "title": "Bleach",
                "source": "Mangadex",
                "download_all_chapters": True,
                "translated_language": ["it"],
                "content_rating": "safe",
                "data_saver": True,
                "no_progress": True,
            },
            {"title": ""},
            {
                "title": "Naruto",
                "source": "fanfox",
                "output": "/tmp/override",
                "proxy": {"http": "http://proxy2.example:8080", "https": "http://proxy2.example:8080"},
                "download_single_chapter": "5",
            },
        ],
    }
    yaml_path.write_text(yaml.dump(payload))
    args = argparse.Namespace(yaml_file=str(yaml_path))

    exit_code = cli.main_yaml(args)

    assert exit_code == 1
    assert len(captured) == 2
    first, second = captured
    assert first.title == "Bleach"
    assert first.source == "mangadex"
    assert first.output == "/tmp/root"
    assert first.proxy == {
        "http": "http://proxy.example:8080",
        "https": "http://proxy.example:8080",
    }
    assert first.download_all_chapters is True
    assert first.no_progress is True
    assert first.options == {
        "translated_language": ["it"],
        "content_rating": ["safe"],
        "data_saver": True,
    }

    assert second.title == "Naruto"
    assert second.source == "fanfox"
    assert second.output == "/tmp/override"
    assert second.proxy == {
        "http": "http://proxy2.example:8080",
        "https": "http://proxy2.example:8080",
    }
    assert second.download_single_chapter == "5"


def test_cmd_parse_requires_subcommand(monkeypatch):
    monkeypatch.setattr(cli.sys, "argv", ["mangapy"])

    try:
        cli.cmd_parse()
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("argparse should reject a missing subcommand")


def test_main_yaml_missing_file_returns_failure(capsys):
    exit_code = cli.main_yaml(argparse.Namespace(yaml_file="/definitely/missing/mangapy.yaml"))

    assert exit_code == 1
    assert "Unable to read YAML configuration" in capsys.readouterr().err


def test_main_yaml_continues_after_invalid_entry(monkeypatch, tmp_path):
    captured = _capture_requests(monkeypatch)
    yaml_path = tmp_path / "sample.yaml"
    yaml_path.write_text(
        yaml.dump(
            {
                "downloads": [
                    {"title": "Broken", "source": "unknown"},
                    {"title": "Bleach", "source": "fanfox"},
                ]
            }
        )
    )

    exit_code = cli.main_yaml(argparse.Namespace(yaml_file=str(yaml_path)))

    assert exit_code == 1
    assert [request.title for request in captured] == ["Bleach"]


def test_main_yaml_continues_after_an_unexpected_download_error(monkeypatch, tmp_path):
    attempted = []

    def fake_download(self, request):
        attempted.append(request.title)
        if request.title == "Broken":
            raise RuntimeError("unexpected failure")
        return DownloadResult(selected_chapters=1, downloaded_chapters=1)

    monkeypatch.setattr(cli.DownloadManager, "download", fake_download)
    yaml_path = tmp_path / "sample.yaml"
    yaml_path.write_text(yaml.dump({"downloads": [{"title": "Broken"}, {"title": "Bleach"}]}))

    exit_code = cli.main_yaml(argparse.Namespace(yaml_file=str(yaml_path)))

    assert exit_code == 1
    assert attempted == ["Broken", "Bleach"]


def test_main_yaml_rejects_conflicting_chapter_selectors(monkeypatch, tmp_path):
    captured = _capture_requests(monkeypatch)
    yaml_path = tmp_path / "sample.yaml"
    yaml_path.write_text(
        yaml.dump(
            {
                "downloads": [
                    {
                        "title": "Bleach",
                        "download_all_chapters": True,
                        "download_single_chapter": "1",
                    }
                ]
            }
        )
    )

    exit_code = cli.main_yaml(argparse.Namespace(yaml_file=str(yaml_path)))

    assert exit_code == 1
    assert captured == []


def test_main_yaml_rejects_non_boolean_flags(monkeypatch, tmp_path):
    captured = _capture_requests(monkeypatch)
    yaml_path = tmp_path / "sample.yaml"
    yaml_path.write_text(yaml.dump({"downloads": [{"title": "Bleach", "pdf": "false"}]}))

    exit_code = cli.main_yaml(argparse.Namespace(yaml_file=str(yaml_path)))

    assert exit_code == 1
    assert captured == []


@pytest.mark.parametrize("unknown_field", ["download_all_chapter", "content_ratings"])
def test_main_yaml_rejects_unknown_download_fields(monkeypatch, tmp_path, unknown_field):
    captured = _capture_requests(monkeypatch)
    yaml_path = tmp_path / "sample.yaml"
    yaml_path.write_text(yaml.dump({"downloads": [{"title": "Bleach", unknown_field: True}]}))

    exit_code = cli.main_yaml(argparse.Namespace(yaml_file=str(yaml_path)))

    assert exit_code == 1
    assert captured == []


def test_main_yaml_rejects_unknown_root_fields(monkeypatch, tmp_path):
    captured = _capture_requests(monkeypatch)
    yaml_path = tmp_path / "sample.yaml"
    yaml_path.write_text(yaml.dump({"ouptut": "/tmp/wrong", "downloads": [{"title": "Bleach"}]}))

    exit_code = cli.main_yaml(argparse.Namespace(yaml_file=str(yaml_path)))

    assert exit_code == 1
    assert captured == []


def test_main_yaml_rejects_mangadex_options_for_fanfox(monkeypatch, tmp_path):
    captured = _capture_requests(monkeypatch)
    yaml_path = tmp_path / "sample.yaml"
    yaml_path.write_text(yaml.dump({"downloads": [{"title": "Bleach", "source": "fanfox", "translated_language": ["it"]}]}))

    exit_code = cli.main_yaml(argparse.Namespace(yaml_file=str(yaml_path)))

    assert exit_code == 1
    assert captured == []


def test_parse_number_rejects_non_finite_values():
    assert download_manager._parse_number("nan") is None
    assert download_manager._parse_number("inf") is None
