from mangapy import terminal
from mangapy.capabilities import ProviderCapabilities
from mangapy.chapter_archiver import ArchiveResult
from mangapy.download_manager import (
    DownloadManager,
    DownloadRequest,
    _select_chapters,
    _select_manga_subdirectory,
    _summarize_archive_results,
)
from mangapy.mangarepository import Chapter, Manga, Page


class DummyChapter(Chapter):
    def __init__(self, chapter_id: str, number: float | None = None):
        super().__init__("http://example.com", chapter_id, number)

    def pages(self):
        return [Page(0, "http://example.com/0.jpg")]


class DummyRepo:
    def __init__(self, max_parallel_chapters: int):
        self._caps = ProviderCapabilities(max_parallel_chapters=max_parallel_chapters, max_parallel_pages=1)
        self.proxies = None

    @property
    def capabilities(self):
        return self._caps

    def image_request_headers(self):
        return None

    def search(self, title, options=None):
        return Manga(title, [DummyChapter("1", 1.0), DummyChapter("2", 2.0)])

    def suggestions(self, title, options=None):
        return []


class MissingRepo(DummyRepo):
    def __init__(self, suggestions: list[str]):
        super().__init__(max_parallel_chapters=1)
        self._suggestions = suggestions

    def search(self, title, options=None):
        return None

    def suggestions(self, title, options=None):
        return self._suggestions


def _downloaded(chapter: Chapter) -> ArchiveResult:
    return ArchiveResult(
        chapter_name=chapter.output_name,
        status="downloaded",
        expected_pages=1,
        saved_pages=1,
    )


def test_download_manager_parallel_chapters(monkeypatch, tmp_path):
    repo = DummyRepo(max_parallel_chapters=2)
    calls = []
    archiver_ids = []
    progress_instances = []

    class RecordingProgress:
        def __init__(self, enabled):
            self.enabled = enabled
            self.entered = 0
            self.exited = 0
            progress_instances.append(self)

        def __enter__(self):
            self.entered += 1
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            self.exited += 1

    monkeypatch.setattr("mangapy.download_manager.get_repository", lambda name: repo)
    monkeypatch.setattr(terminal, "DownloadProgress", RecordingProgress)

    def fake_archive(archiver, chapter, pdf, headers):
        calls.append(chapter.chapter_id)
        archiver_ids.append(id(archiver))
        assert archiver.progress is progress_instances[0]
        return _downloaded(chapter)

    monkeypatch.setattr("mangapy.download_manager._archive_with_archiver", fake_archive)

    request = DownloadRequest(
        title="dummy",
        source="fanfox",
        output=str(tmp_path),
        download_all_chapters=True,
    )
    result = DownloadManager().download(request)

    assert sorted(calls) == ["1", "2"]
    assert len(set(archiver_ids)) == 1
    assert len(progress_instances) == 1
    assert progress_instances[0].enabled
    assert progress_instances[0].entered == 1
    assert progress_instances[0].exited == 1
    assert result.succeeded
    assert result.downloaded_chapters == 2


def test_download_manager_sequential_chapters(monkeypatch, tmp_path):
    repo = DummyRepo(max_parallel_chapters=1)
    calls = []

    monkeypatch.setattr("mangapy.download_manager.get_repository", lambda name: repo)

    def fake_archive_with_archiver(archiver, chapter, pdf, headers):
        calls.append(chapter.chapter_id)
        return _downloaded(chapter)

    monkeypatch.setattr("mangapy.download_manager._archive_with_archiver", fake_archive_with_archiver)

    request = DownloadRequest(
        title="dummy",
        source="fanfox",
        output=str(tmp_path),
        download_all_chapters=True,
    )
    result = DownloadManager().download(request)

    assert sorted(calls) == ["1", "2"]
    assert result.succeeded


def test_download_manager_prints_suggestions_for_missing_manga(monkeypatch, capsys):
    repo = MissingRepo(["One Piece", "One Punch-Man"])
    monkeypatch.setattr("mangapy.download_manager.get_repository", lambda name: repo)

    request = DownloadRequest(
        title="one pice",
        source="fanfox",
        output="/tmp",
    )
    result = DownloadManager().download(request)

    output = capsys.readouterr().out
    assert "Manga one pice doesn't exist" in output
    assert "Did you mean one of these?" in output
    assert "One Piece" in output
    assert "One Punch-Man" in output
    assert not result.succeeded


def test_download_manager_passes_proxy_to_repository_and_archiver(monkeypatch, tmp_path):
    repo = DummyRepo(max_parallel_chapters=1)
    observed = {}
    proxy = {
        "http": "http://proxy.example:8080",
        "https": "http://proxy.example:8080",
    }
    monkeypatch.setattr("mangapy.download_manager.get_repository", lambda name: repo)

    def fake_archive_with_archiver(archiver, chapter, pdf, headers):
        observed["archiver_proxies"] = archiver.proxies
        return _downloaded(chapter)

    monkeypatch.setattr("mangapy.download_manager._archive_with_archiver", fake_archive_with_archiver)

    result = DownloadManager().download(
        DownloadRequest(
            title="dummy",
            source="fanfox",
            output=str(tmp_path),
            proxy=proxy,
        )
    )

    assert result.succeeded
    assert repo.proxies == proxy
    assert observed["archiver_proxies"] == proxy


def test_download_result_reports_partial_failure():
    result = _summarize_archive_results(
        [
            ArchiveResult(chapter_name="1", status="downloaded", expected_pages=1, saved_pages=1),
            ArchiveResult(chapter_name="2", status="failed", expected_pages=2, saved_pages=1, message="missing page"),
        ]
    )

    assert not result.succeeded
    assert result.selected_chapters == 2
    assert result.downloaded_chapters == 1
    assert result.failed_chapters == 1


def test_download_result_rejects_inconsistent_success_counts():
    result = _summarize_archive_results([ArchiveResult(chapter_name="1", status="downloaded", expected_pages=2, saved_pages=1)])

    assert not result.succeeded
    assert result.downloaded_chapters == 0
    assert result.failed_chapters == 1


def test_download_manager_invalid_source_returns_failure(monkeypatch):
    def missing_repository(name):
        raise ValueError(f"Source {name} is missing")

    monkeypatch.setattr("mangapy.download_manager.get_repository", missing_repository)

    result = DownloadManager().download(DownloadRequest(title="dummy", source="missing", output="/tmp"))

    assert not result.succeeded
    assert result.error == "Source missing is missing"


def test_download_manager_rejects_conflicting_selection(monkeypatch):
    repo = DummyRepo(max_parallel_chapters=1)
    monkeypatch.setattr("mangapy.download_manager.get_repository", lambda name: repo)

    result = DownloadManager().download(
        DownloadRequest(
            title="dummy",
            source="fanfox",
            output="/tmp",
            download_all_chapters=True,
            download_single_chapter="1",
        )
    )

    assert not result.succeeded
    assert result.error == "Chapter selection fields are mutually exclusive"


def test_download_manager_returns_a_result_when_output_initialization_fails(monkeypatch, tmp_path):
    repo = DummyRepo(max_parallel_chapters=1)
    monkeypatch.setattr("mangapy.download_manager.get_repository", lambda name: repo)
    blocked_output = tmp_path / "not-a-directory"
    blocked_output.write_text("occupied")

    result = DownloadManager().download(DownloadRequest(title="dummy", source="fanfox", output=str(blocked_output)))

    assert not result.succeeded
    assert result.selected_chapters == 1
    assert result.error is not None
    assert "Unable to initialize chapter downloads" in result.error


def test_download_manager_rejects_symlinked_generated_directories(monkeypatch, tmp_path):
    repo = DummyRepo(max_parallel_chapters=1)
    monkeypatch.setattr("mangapy.download_manager.get_repository", lambda name: repo)
    outside = tmp_path / "outside"
    outside.mkdir()
    output = tmp_path / "output"
    output.mkdir()
    (output / "fanfox").symlink_to(outside, target_is_directory=True)

    result = DownloadManager().download(DownloadRequest(title="dummy", source="fanfox", output=str(output)))

    assert not result.succeeded
    assert result.error is not None
    assert "not a real directory" in result.error
    assert list(outside.iterdir()) == []


def test_download_manager_rejects_a_symlinked_output_root(monkeypatch, tmp_path):
    repo = DummyRepo(max_parallel_chapters=1)
    monkeypatch.setattr("mangapy.download_manager.get_repository", lambda name: repo)
    outside = tmp_path / "outside"
    outside.mkdir()
    output = tmp_path / "output-link"
    output.symlink_to(outside, target_is_directory=True)

    result = DownloadManager().download(DownloadRequest(title="dummy", source="fanfox", output=str(output)))

    assert not result.succeeded
    assert result.error is not None
    assert "not a real directory" in result.error
    assert list(outside.iterdir()) == []


def test_existing_legacy_ascii_slug_is_reused(tmp_path):
    legacy_path = tmp_path / "fanfox" / "pok_mon"
    legacy_path.mkdir(parents=True)
    manga = Manga("Pokémon", [DummyChapter("1", 1.0)])

    selected = _select_manga_subdirectory(str(tmp_path), "fanfox", manga)

    assert manga.subdirectory == "pokémon"
    assert selected == "pok_mon"


def test_chapter_range_excludes_non_finite_provider_numbers():
    finite = DummyChapter("1", 1.0)
    not_a_number = DummyChapter("nan", float("nan"))
    infinity = DummyChapter("infinity", float("inf"))
    manga = Manga("Example", [finite, not_a_number, infinity])
    request = DownloadRequest(title="Example", source="fanfox", output="/unused", download_chapters="0-2")

    assert _select_chapters(manga, request) == [finite]
