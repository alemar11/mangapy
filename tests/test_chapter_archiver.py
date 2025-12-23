from mangapy.chapter_archiver import ChapterArchiver
from mangapy.mangarepository import Page


class DummyChapter:
    def __init__(self, number, pages):
        self.number = number
        self._pages = pages

    def pages(self):
        return self._pages


def test_archive_uses_normalized_chapter_dir(tmp_path, monkeypatch):
    archiver = ChapterArchiver(str(tmp_path), max_workers=1)
    monkeypatch.setattr(ChapterArchiver, "_fetch_image", lambda self, url, headers: b"data")

    chapter = DummyChapter(1.0, [Page(0, "http://example.com/1.jpg")])
    archiver.archive(chapter, pdf=False, headers=None)

    expected_file = tmp_path / "images" / "1" / "0.jpg"
    assert expected_file.is_file()
    assert not (tmp_path / "images" / "1.0").exists()
