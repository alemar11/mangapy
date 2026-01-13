from mangapy.capabilities import ProviderCapabilities
from mangapy.download_manager import DownloadManager, DownloadRequest, _archive_chapter, _archive_with_archiver
from mangapy.mangarepository import Manga, Chapter, Page


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


def test_download_manager_parallel_chapters(monkeypatch):
    repo = DummyRepo(max_parallel_chapters=2)
    calls = []

    monkeypatch.setattr("mangapy.download_manager.get_repository", lambda name: repo)

    def fake_archive(directory, max_parallel_pages, chapter, pdf, headers, **kwargs):
        calls.append(chapter.chapter_id)

    monkeypatch.setattr("mangapy.download_manager._archive_chapter", fake_archive)

    request = DownloadRequest(
        title="dummy",
        source="fanfox",
        output="/tmp",
        download_all_chapters=True,
    )
    DownloadManager().download(request)

    assert sorted(calls) == ["1", "2"]


def test_download_manager_sequential_chapters(monkeypatch):
    repo = DummyRepo(max_parallel_chapters=1)
    calls = []

    monkeypatch.setattr("mangapy.download_manager.get_repository", lambda name: repo)

    def fake_archive_with_archiver(archiver, chapter, pdf, headers):
        calls.append(chapter.chapter_id)

    monkeypatch.setattr("mangapy.download_manager._archive_with_archiver", fake_archive_with_archiver)

    request = DownloadRequest(
        title="dummy",
        source="fanfox",
        output="/tmp",
        download_all_chapters=True,
    )
    DownloadManager().download(request)

    assert sorted(calls) == ["1", "2"]
