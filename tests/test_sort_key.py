from mangapy.mangadex import _chapter_sort_key as mangadex_chapter_sort_key
from mangapy.mangarepository import chapter_sort_key


def test_chapter_sort_key_numeric_before_special():
    keys = [
        chapter_sort_key("10.E", None),
        chapter_sort_key("2", 2.0),
    ]
    assert sorted(keys)[0] == chapter_sort_key("2", 2.0)


def test_chapter_sort_key_is_comparable_for_mixed_values():
    keys = [
        chapter_sort_key("10.E", None),
        chapter_sort_key("nan", float("nan")),
        chapter_sort_key("2", 2.0),
    ]

    assert sorted(keys)[0] == chapter_sort_key("2", 2.0)


def test_mangadex_chapter_sort_key_is_comparable_with_optional_volumes():
    keys = [
        mangadex_chapter_sort_key("2", "1", "with-volume"),
        mangadex_chapter_sort_key(None, "2", "without-volume"),
        mangadex_chapter_sort_key("1", None, "volume-special"),
        mangadex_chapter_sort_key(None, "extra", "special"),
    ]

    assert sorted(keys) == [
        mangadex_chapter_sort_key("2", "1", "with-volume"),
        mangadex_chapter_sort_key(None, "2", "without-volume"),
        mangadex_chapter_sort_key("1", None, "volume-special"),
        mangadex_chapter_sort_key(None, "extra", "special"),
    ]
