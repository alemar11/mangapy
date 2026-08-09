from mangapy.mangarepository import Chapter, Manga


class DummyChapter(Chapter):
    def pages(self):
        return []


def test_chapter_output_name_preserves_existing_numeric_names():
    assert DummyChapter("https://example.test/1", "001", 1.0).output_name == "1"
    assert DummyChapter("https://example.test/1.5", "001.5", 1.5).output_name == "1.5"
    assert DummyChapter("https://example.test/special", "087.Extra").output_name == "087.Extra"
    assert DummyChapter("https://example.test/nan", "special", float("nan")).output_name == "special"


def test_manga_subdirectory_preserves_unicode_letters():
    assert Manga("進撃の巨人", []).subdirectory == "進撃の巨人"
    assert Manga("  L'ÉTÉ — 2026  ", []).subdirectory == "l_été_2026"


def test_manga_subdirectory_has_stable_nonempty_fallback():
    first = Manga("🔥", []).subdirectory
    second = Manga("🔥", []).subdirectory

    assert first == second
    assert first.startswith("manga_")
    assert first != Manga("✨", []).subdirectory


def test_manga_subdirectory_is_portable_and_bounded():
    ascii_name = Manga("a" * 300, []).subdirectory
    unicode_name = Manga("章" * 100, []).subdirectory

    assert len(ascii_name.encode("utf-8")) <= 180
    assert len(unicode_name.encode("utf-8")) <= 180
    assert ascii_name == Manga("a" * 300, []).subdirectory
    assert unicode_name == Manga("章" * 100, []).subdirectory
    assert Manga("CON", []).subdirectory == "_con"


def test_last_downloadable_chapter_prefers_highest_finite_number():
    latest_numeric = DummyChapter("https://example.test/652", "652", 652.0)
    special = DummyChapter("https://example.test/extra", "087.Extra")
    external = DummyChapter("https://example.test/700", "700", 700.0)
    external.external_url = "https://external.test/chapter"
    empty = DummyChapter("https://example.test/701", "701", 701.0)
    empty.pages_count = 0
    manga = Manga("Example", [latest_numeric, special, external, empty])

    assert manga.last_chapter is empty
    assert manga.last_downloadable_chapter is latest_numeric


def test_last_downloadable_chapter_falls_back_to_last_special():
    first = DummyChapter("https://example.test/a", "special-a")
    second = DummyChapter("https://example.test/b", "special-b")

    assert Manga("Example", [first, second]).last_downloadable_chapter is second


def test_last_downloadable_chapter_is_none_without_hosted_pages():
    external = DummyChapter("https://example.test/external", "external")
    external.external_url = "https://external.test/chapter"
    empty = DummyChapter("https://example.test/empty", "empty")
    empty.pages_count = 0

    assert Manga("Example", [external, empty]).last_downloadable_chapter is None
