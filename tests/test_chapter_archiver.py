from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest
import requests
from PIL import Image

from mangapy.chapter_archiver import ArchiveResult, ChapterArchiver, _retry_delay
from mangapy.mangarepository import Page

_UNSET = object()


class DummyChapter:
    def __init__(
        self,
        number,
        pages,
        *,
        output_name=None,
        chapter_id=None,
        external_url=None,
        pages_count=_UNSET,
    ):
        self.number = number
        self._pages = pages
        self.chapter_id = chapter_id if chapter_id is not None else str(number)
        self.pages_count = len(pages) if pages_count is _UNSET else pages_count
        if output_name is not None:
            self.output_name = output_name
        if external_url is not None:
            self.external_url = external_url

    def pages(self):
        return self._pages


def test_archive_uses_normalized_chapter_dir(tmp_path, monkeypatch):
    archiver = ChapterArchiver(str(tmp_path), max_workers=1)
    monkeypatch.setattr(ChapterArchiver, "_fetch_image", lambda self, url, headers: _png_bytes())

    chapter = DummyChapter(1.0, [Page(0, "http://example.com/1.jpg")])
    result = archiver.archive(chapter, pdf=False, headers=None)

    expected_file = tmp_path / "images" / "1" / "0.jpg"
    assert expected_file.is_file()
    assert not (tmp_path / "images" / "1.0").exists()
    assert result == ArchiveResult("downloaded", "1", 1, 1, "Downloaded all 1 pages for chapter 1.")
    assert result.succeeded


def _png_bytes():
    image = Image.new("RGB", (10, 10), color=(255, 0, 0))
    buf = BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def _transparent_png_bytes():
    image = Image.new("RGBA", (10, 10), color=(255, 0, 0, 128))
    buf = BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def _jpeg_bytes():
    image = Image.new("RGB", (10, 10), color=(255, 0, 0))
    buf = BytesIO()
    image.save(buf, format="JPEG")
    return buf.getvalue()


def test_archive_pdf_creates_pdf_and_cleans_images(tmp_path, monkeypatch):
    archiver = ChapterArchiver(str(tmp_path), max_workers=1)
    image_bytes = _png_bytes()
    monkeypatch.setattr(ChapterArchiver, "_fetch_image", lambda self, url, headers: image_bytes)

    chapter = DummyChapter(
        1.0,
        [
            Page(0, "http://example.com/0.png"),
            Page(1, "http://example.com/1.png"),
        ],
    )
    result = archiver.archive(chapter, pdf=True, headers=None)

    assert (tmp_path / "pdf" / "1.pdf").is_file()
    assert not (tmp_path / ".images" / "1").exists()
    assert result.status == "downloaded"
    assert result.expected_pages == result.saved_pages == 2


def test_archive_pdf_handles_transparent_png(tmp_path, monkeypatch):
    archiver = ChapterArchiver(str(tmp_path), max_workers=1)
    image_bytes = _transparent_png_bytes()
    monkeypatch.setattr(ChapterArchiver, "_fetch_image", lambda self, url, headers: image_bytes)

    chapter = DummyChapter(2.0, [Page(0, "http://example.com/0.png")])
    result = archiver.archive(chapter, pdf=True, headers=None)

    assert (tmp_path / "pdf" / "2.pdf").is_file()
    assert not (tmp_path / ".images" / "2").exists()
    assert result.succeeded


def test_archive_prefers_unicode_output_name_and_sanitizes_path_traversal(tmp_path, monkeypatch):
    archiver = ChapterArchiver(str(tmp_path), max_workers=1)
    monkeypatch.setattr(ChapterArchiver, "_fetch_image", lambda self, url, headers: _png_bytes())
    chapter = DummyChapter(
        99.0,
        [Page(0, "https://example.com/0.jpg")],
        output_name="../../第 １ 話/../special",
        chapter_id="unsafe-id",
    )

    result = archiver.archive(chapter, pdf=False, headers=None)

    assert result.status == "downloaded"
    assert result.chapter_name == "第 1 話_.._special"
    assert (tmp_path / "images" / result.chapter_name / "0.jpg").is_file()
    assert not (tmp_path.parent / "special").exists()


def test_archive_limits_long_unicode_output_name_with_a_stable_hash(tmp_path, monkeypatch):
    archiver = ChapterArchiver(str(tmp_path), max_workers=1)
    monkeypatch.setattr(ChapterArchiver, "_fetch_image", lambda self, url, headers: _png_bytes())
    output_name = "章" * 200
    chapter = DummyChapter(1.0, [Page(0, "https://example.com/0.jpg")], output_name=output_name)

    first_result = archiver.archive(chapter, pdf=False, headers=None)
    second_result = archiver.archive(chapter, pdf=False, headers=None)

    assert first_result.status == "downloaded"
    assert second_result.status == "already_exists"
    assert first_result.chapter_name == second_result.chapter_name
    assert len(first_result.chapter_name.encode("utf-8")) <= 180
    assert first_result.chapter_name != output_name
    assert (tmp_path / "images" / first_result.chapter_name / "0.jpg").is_file()


def test_archive_refuses_symlinked_chapter_directory(tmp_path, monkeypatch):
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    images_path = tmp_path / "images"
    images_path.mkdir()
    (images_path / "safe").symlink_to(outside, target_is_directory=True)
    archiver = ChapterArchiver(str(tmp_path), max_workers=1)
    fetch_calls = []

    def fetch_image(self, url, headers):
        fetch_calls.append(url)
        return b"data"

    monkeypatch.setattr(ChapterArchiver, "_fetch_image", fetch_image)
    chapter = DummyChapter(1.0, [Page(0, "https://example.com/0.jpg")], output_name="safe")

    result = archiver.archive(chapter, pdf=False, headers=None)

    assert result.status == "failed"
    assert not result.succeeded
    assert "symlink" in result.message
    assert fetch_calls == []
    assert list(outside.iterdir()) == []


def test_archiver_refuses_a_symlink_as_its_configured_root(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    linked_root = tmp_path / "linked-root"
    linked_root.symlink_to(outside, target_is_directory=True)

    with pytest.raises(OSError, match="not a real directory"):
        ChapterArchiver(str(linked_root))


def test_partial_pdf_is_not_published_and_retry_reuses_saved_images(tmp_path, monkeypatch):
    archiver = ChapterArchiver(str(tmp_path), max_workers=1, retry_enabled=False)
    image_bytes = _png_bytes()
    calls = {"0": 0, "1": 0}

    def fetch_image(self, url, headers):
        page = Path(url).stem
        calls[page] += 1
        if page == "1" and calls[page] == 1:
            return None
        return image_bytes

    monkeypatch.setattr(ChapterArchiver, "_fetch_image", fetch_image)
    chapter = DummyChapter(
        1.0,
        [Page(0, "https://example.com/0.png"), Page(1, "https://example.com/1.png")],
    )

    first_result = archiver.archive(chapter, pdf=True, headers=None)

    assert first_result.status == "failed"
    assert first_result.expected_pages == 2
    assert first_result.saved_pages == 1
    assert not (tmp_path / "pdf" / "1.pdf").exists()
    assert (tmp_path / ".images" / "1" / "0.png").is_file()

    second_result = archiver.archive(chapter, pdf=True, headers=None)

    assert second_result.status == "downloaded"
    assert second_result.saved_pages == 2
    assert calls == {"0": 1, "1": 2}
    assert (tmp_path / "pdf" / "1.pdf").is_file()
    assert not (tmp_path / ".images" / "1").exists()


def test_advertised_page_count_mismatch_fails_without_publishing_pdf(tmp_path, monkeypatch):
    archiver = ChapterArchiver(str(tmp_path), max_workers=1)
    fetch_calls = []

    def fetch_image(self, url, headers):
        fetch_calls.append(url)
        return _png_bytes()

    monkeypatch.setattr(ChapterArchiver, "_fetch_image", fetch_image)
    chapter = DummyChapter(
        1.0,
        [Page(0, "https://example.com/0.png")],
        pages_count=2,
    )

    result = archiver.archive(chapter, pdf=True, headers=None)

    assert result.status == "failed"
    assert result.expected_pages == 2
    assert result.saved_pages == 0
    assert "returned 1 pages" in result.message
    assert fetch_calls == []
    assert not (tmp_path / "pdf" / "1.pdf").exists()


def test_advertised_pages_missing_is_a_failure_not_unavailable(tmp_path):
    chapter = DummyChapter(1.0, [], pages_count=2)

    result = ChapterArchiver(str(tmp_path)).archive(chapter, pdf=True, headers=None)

    assert result.status == "failed"
    assert result.expected_pages == 2
    assert result.saved_pages == 0
    assert "returned no pages" in result.message


def test_page_discovery_network_failure_is_not_reported_as_unavailable(tmp_path):
    chapter = DummyChapter(1.0, None, pages_count=None)

    result = ChapterArchiver(str(tmp_path)).archive(chapter, pdf=False, headers=None)

    assert result.status == "failed"
    assert "page discovery failed" in result.message


def test_partial_legacy_pdf_is_replaced_using_the_advertised_page_count(tmp_path, monkeypatch):
    archiver = ChapterArchiver(str(tmp_path), max_workers=1)
    fetch_calls = []

    def fetch_image(self, url, headers):
        fetch_calls.append(url)
        return _png_bytes()

    monkeypatch.setattr(ChapterArchiver, "_fetch_image", fetch_image)
    one_page = DummyChapter(1.0, [Page(0, "https://example.com/0.png")])
    two_pages = DummyChapter(
        1.0,
        [Page(0, "https://example.com/0.png"), Page(1, "https://example.com/1.png")],
        pages_count=2,
    )

    assert archiver.archive(one_page, pdf=True, headers=None).status == "downloaded"
    result = archiver.archive(two_pages, pdf=True, headers=None)

    assert result.status == "downloaded"
    assert result.expected_pages == result.saved_pages == 2
    assert archiver._valid_pdf_page_count(tmp_path / "pdf" / "1.pdf") == 2
    assert fetch_calls == [
        "https://example.com/0.png",
        "https://example.com/0.png",
        "https://example.com/1.png",
    ]


def test_legacy_pdf_with_unknown_count_is_verified_against_provider_pages(tmp_path, monkeypatch):
    archiver = ChapterArchiver(str(tmp_path), max_workers=1)
    fetch_calls = []

    def fetch_image(self, url, headers):
        fetch_calls.append(url)
        return _png_bytes()

    monkeypatch.setattr(ChapterArchiver, "_fetch_image", fetch_image)
    one_page = DummyChapter(1.0, [Page(0, "https://example.com/0.png")], pages_count=None)
    two_pages = DummyChapter(
        1.0,
        [Page(0, "https://example.com/0.png"), Page(1, "https://example.com/1.png")],
        pages_count=None,
    )

    assert archiver.archive(one_page, pdf=True, headers=None).status == "downloaded"
    result = archiver.archive(two_pages, pdf=True, headers=None)

    assert result.status == "downloaded"
    assert result.expected_pages == result.saved_pages == 2
    assert archiver._valid_pdf_page_count(tmp_path / "pdf" / "1.pdf") == 2
    assert fetch_calls == [
        "https://example.com/0.png",
        "https://example.com/0.png",
        "https://example.com/1.png",
    ]


def test_existing_complete_pdf_remains_idempotent_if_chapter_becomes_external(tmp_path, monkeypatch):
    archiver = ChapterArchiver(str(tmp_path), max_workers=1)
    fetch_calls = []

    def fetch_image(self, url, headers):
        fetch_calls.append(url)
        return _png_bytes()

    monkeypatch.setattr(ChapterArchiver, "_fetch_image", fetch_image)
    hosted = DummyChapter(1.0, [Page(0, "https://example.com/0.png")])
    external = DummyChapter(
        1.0,
        [],
        pages_count=0,
        external_url="https://external.example/chapter",
    )

    assert archiver.archive(hosted, pdf=True, headers=None).status == "downloaded"
    result = archiver.archive(external, pdf=True, headers=None)

    assert result.status == "already_exists"
    assert result.succeeded
    assert fetch_calls == ["https://example.com/0.png"]


def test_images_are_atomic_zero_byte_files_are_retried_and_complete_download_is_idempotent(tmp_path, monkeypatch):
    chapter_path = tmp_path / "images" / "1"
    chapter_path.mkdir(parents=True)
    (chapter_path / "0.jpg").touch()
    archiver = ChapterArchiver(str(tmp_path), max_workers=1)
    calls = []

    def fetch_image(self, url, headers):
        calls.append(url)
        return _png_bytes()

    monkeypatch.setattr(ChapterArchiver, "_fetch_image", fetch_image)
    chapter = DummyChapter(1.0, [Page(0, "https://example.com/0.jpg")])

    first_result = archiver.archive(chapter, pdf=False, headers=None)
    second_result = archiver.archive(chapter, pdf=False, headers=None)

    assert first_result.status == "downloaded"
    assert second_result.status == "already_exists"
    assert second_result.succeeded
    assert calls == ["https://example.com/0.jpg"]
    assert (chapter_path / "0.jpg").read_bytes() == _png_bytes()
    assert list(chapter_path.glob("*.tmp")) == []


def test_failed_atomic_image_replace_leaves_no_final_or_temporary_file(tmp_path, monkeypatch):
    archiver = ChapterArchiver(str(tmp_path), max_workers=1)
    monkeypatch.setattr(ChapterArchiver, "_fetch_image", lambda self, url, headers: _png_bytes())

    def fail_replace(source, destination):
        raise OSError("replace failed")

    monkeypatch.setattr("mangapy.chapter_archiver.os.replace", fail_replace)
    chapter = DummyChapter(1.0, [Page(0, "https://example.com/0.jpg")])

    result = archiver.archive(chapter, pdf=False, headers=None)

    chapter_path = tmp_path / "images" / "1"
    assert result.status == "failed"
    assert result.saved_pages == 0
    assert not (chapter_path / "0.jpg").exists()
    assert list(chapter_path.glob("*.tmp")) == []


def test_pdf_publication_is_atomic_and_preserves_images_on_replace_failure(tmp_path, monkeypatch):
    image_path = tmp_path / ".images" / "1"
    image_path.mkdir(parents=True)
    (image_path / "0.png").write_bytes(_png_bytes())
    archiver = ChapterArchiver(str(tmp_path), max_workers=1)
    monkeypatch.setattr(
        ChapterArchiver,
        "_fetch_image",
        lambda self, url, headers: pytest.fail("existing image should be reused"),
    )

    def fail_replace(source, destination):
        raise OSError("replace failed")

    monkeypatch.setattr("mangapy.chapter_archiver.os.replace", fail_replace)
    chapter = DummyChapter(1.0, [Page(0, "https://example.com/0.png")])

    result = archiver.archive(chapter, pdf=True, headers=None)

    assert result.status == "failed"
    assert result.saved_pages == 1
    assert not (tmp_path / "pdf" / "1.pdf").exists()
    assert (image_path / "0.png").is_file()
    assert list((tmp_path / "pdf").glob("*.tmp")) == []


def test_corrupt_cached_image_is_refetched_before_pdf_conversion(tmp_path, monkeypatch):
    image_path = tmp_path / ".images" / "1" / "0.png"
    image_path.parent.mkdir(parents=True)
    image_path.write_bytes(b"corrupt but non-empty")
    archiver = ChapterArchiver(str(tmp_path), max_workers=1)
    fetch_calls = []

    def fetch_image(self, url, headers):
        fetch_calls.append(url)
        return _png_bytes()

    monkeypatch.setattr(ChapterArchiver, "_fetch_image", fetch_image)
    chapter = DummyChapter(1.0, [Page(0, "https://example.com/0.png")])

    result = archiver.archive(chapter, pdf=True, headers=None)

    assert result.status == "downloaded"
    assert fetch_calls == ["https://example.com/0.png"]
    assert not image_path.exists()
    assert (tmp_path / "pdf" / "1.pdf").exists()


def test_valid_pdf_is_skipped_but_invalid_pdf_is_replaced(tmp_path, monkeypatch):
    archiver = ChapterArchiver(str(tmp_path), max_workers=1)
    image_bytes = _png_bytes()
    fetch_calls = []

    def fetch_image(self, url, headers):
        fetch_calls.append(url)
        return image_bytes

    monkeypatch.setattr(ChapterArchiver, "_fetch_image", fetch_image)
    chapter = DummyChapter(1.0, [Page(0, "https://example.com/0.png")])
    pdf_path = tmp_path / "pdf" / "1.pdf"
    pdf_path.parent.mkdir()
    pdf_path.write_bytes(b"not a pdf")

    first_result = archiver.archive(chapter, pdf=True, headers=None)
    first_pdf = pdf_path.read_bytes()
    second_result = archiver.archive(chapter, pdf=True, headers=None)

    assert first_result.status == "downloaded"
    assert first_pdf.startswith(b"%PDF-")
    assert b"%%EOF" in first_pdf[-1024:]
    assert second_result.status == "already_exists"
    assert second_result.expected_pages == second_result.saved_pages == 1
    assert fetch_calls == ["https://example.com/0.png"]


def test_chapter_lock_serializes_duplicate_archives(tmp_path, monkeypatch):
    archiver = ChapterArchiver(str(tmp_path), max_workers=1)
    image_bytes = _png_bytes()
    fetch_calls = []

    def fetch_image(self, url, headers):
        fetch_calls.append(url)
        return image_bytes

    monkeypatch.setattr(ChapterArchiver, "_fetch_image", fetch_image)
    chapter = DummyChapter(1.0, [Page(0, "https://example.com/0.png")])

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: archiver.archive(chapter, pdf=False, headers=None), range(2)))

    assert {result.status for result in results} == {"downloaded", "already_exists"}
    assert fetch_calls == ["https://example.com/0.png"]


def test_configured_proxies_are_applied_to_every_thread_local_session(tmp_path):
    proxies = {"http": "http://proxy.example:8080", "https": "http://proxy.example:8080"}
    archiver = ChapterArchiver(str(tmp_path), proxies=proxies)

    with ThreadPoolExecutor(max_workers=2) as executor:
        session_proxies = list(executor.map(lambda _: dict(archiver._get_session().proxies), range(2)))

    assert session_proxies == [proxies, proxies]


@pytest.mark.parametrize(
    ("chapter", "expected_message"),
    [
        (DummyChapter(1.0, [], external_url="https://example.com/external"), "hosted externally"),
        (DummyChapter(2.0, [], pages_count=0), "no pages available"),
        (DummyChapter(3.0, [], pages_count=None), "doesn't have any pages"),
    ],
)
def test_unavailable_chapters_return_structured_results(tmp_path, chapter, expected_message):
    result = ChapterArchiver(str(tmp_path)).archive(chapter, pdf=False, headers=None)

    assert result.status == "unavailable"
    assert not result.succeeded
    assert result.saved_pages == 0
    assert expected_message in result.message


def test_empty_response_fails_without_creating_an_image(tmp_path, monkeypatch):
    archiver = ChapterArchiver(str(tmp_path), max_workers=1)
    monkeypatch.setattr(ChapterArchiver, "_fetch_image", lambda self, url, headers: b"")
    chapter = DummyChapter(1.0, [Page(0, "https://example.com/0.jpg")])

    result = archiver.archive(chapter, pdf=False, headers=None)

    assert result.status == "failed"
    assert result.expected_pages == 1
    assert result.saved_pages == 0
    assert not (tmp_path / "images" / "1" / "0.jpg").exists()


def test_html_response_is_not_published_or_cached_as_an_image(tmp_path, monkeypatch):
    archiver = ChapterArchiver(str(tmp_path), max_workers=1)
    monkeypatch.setattr(ChapterArchiver, "_fetch_image", lambda self, url, headers: b"<html>upstream error</html>")
    chapter = DummyChapter(1.0, [Page(0, "https://example.com/0.jpg")])

    result = archiver.archive(chapter, pdf=False, headers=None)

    assert result.status == "failed"
    assert not result.succeeded
    assert not (tmp_path / "images" / "1" / "0.jpg").exists()


def test_truncated_image_is_not_published(tmp_path, monkeypatch):
    archiver = ChapterArchiver(str(tmp_path), max_workers=1)
    monkeypatch.setattr(ChapterArchiver, "_fetch_image", lambda self, url, headers: _jpeg_bytes()[:-2])
    chapter = DummyChapter(1.0, [Page(0, "https://example.com/0.jpg")])

    result = archiver.archive(chapter, pdf=False, headers=None)

    assert result.status == "failed"
    assert not (tmp_path / "images" / "1" / "0.jpg").exists()


def test_incomplete_success_status_does_not_satisfy_archive_result_contract():
    result = ArchiveResult("downloaded", "1", expected_pages=2, saved_pages=1)

    assert not result.succeeded


def test_page_errors_are_aggregated_without_stopping_other_downloads(tmp_path, monkeypatch):
    archiver = ChapterArchiver(str(tmp_path), max_workers=2)
    calls = []

    def fetch_image(self, url, headers):
        calls.append(url)
        if url.endswith("0.jpg"):
            raise RuntimeError("broken page")
        return _png_bytes()

    monkeypatch.setattr(ChapterArchiver, "_fetch_image", fetch_image)
    chapter = DummyChapter(
        1.0,
        [Page(0, "https://example.com/0.jpg"), Page(1, "https://example.com/1.jpg")],
    )

    result = archiver.archive(chapter, pdf=False, headers=None)

    assert result.status == "failed"
    assert result.expected_pages == 2
    assert result.saved_pages == 1
    assert sorted(calls) == ["https://example.com/0.jpg", "https://example.com/1.jpg"]
    assert (tmp_path / "images" / "1" / "1.jpg").is_file()


def test_duplicate_page_targets_fail_before_downloading(tmp_path, monkeypatch):
    archiver = ChapterArchiver(str(tmp_path), max_workers=2)
    fetch_calls = []

    def fetch_image(self, url, headers):
        fetch_calls.append(url)
        return _png_bytes()

    monkeypatch.setattr(ChapterArchiver, "_fetch_image", fetch_image)
    chapter = DummyChapter(
        1.0,
        [Page(0, "https://example.com/first.png"), Page(0, "https://example.com/second.png")],
    )

    result = archiver.archive(chapter, pdf=False, headers=None)

    assert result.status == "failed"
    assert result.saved_pages == 0
    assert "duplicate page output names" in result.message
    assert fetch_calls == []


def test_successful_image_run_removes_files_not_in_the_current_feed(tmp_path, monkeypatch):
    archiver = ChapterArchiver(str(tmp_path), max_workers=1)
    monkeypatch.setattr(ChapterArchiver, "_fetch_image", lambda self, url, headers: _png_bytes())
    original = DummyChapter(
        1.0,
        [Page(0, "https://example.com/0.png"), Page(1, "https://example.com/1.png")],
    )
    reduced = DummyChapter(1.0, [Page(0, "https://example.com/0.png")])

    assert archiver.archive(original, pdf=False, headers=None).status == "downloaded"
    chapter_path = tmp_path / "images" / "1"
    (chapter_path / "notes.txt").write_text("keep me")
    (chapter_path / "cover.png").write_bytes(_png_bytes())
    result = archiver.archive(reduced, pdf=False, headers=None)

    assert result.status == "already_exists"
    assert (chapter_path / "0.png").is_file()
    assert not (chapter_path / "1.png").exists()
    assert (chapter_path / "notes.txt").is_file()
    assert (chapter_path / "cover.png").is_file()


def test_fetch_image_does_not_sleep_after_last_retry(tmp_path, monkeypatch):
    archiver = ChapterArchiver(str(tmp_path), retry_enabled=True)
    session = SimpleNamespace(get=lambda *args, **kwargs: (_ for _ in ()).throw(requests.ConnectionError("offline")))
    sleeps = []
    monkeypatch.setattr(archiver, "_get_session", lambda: session)
    monkeypatch.setattr("mangapy.chapter_archiver.time.sleep", sleeps.append)

    assert archiver._fetch_image("https://example.com/0.jpg", headers=None) is None
    assert len(sleeps) == 2


@pytest.mark.parametrize("retry_after", ["nan", "inf", "-inf"])
def test_retry_after_rejects_non_finite_values(retry_after):
    response = requests.Response()
    response.headers["Retry-After"] = retry_after

    delay = _retry_delay(0, response)

    assert 1 <= delay <= 1.2


def test_retry_after_is_capped():
    response = requests.Response()
    response.headers["Retry-After"] = "3600"

    assert _retry_delay(0, response) == 30.0
