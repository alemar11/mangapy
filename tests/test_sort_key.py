from mangapy.mangarepository import chapter_sort_key


def test_chapter_sort_key_numeric_before_special():
    keys = [
        chapter_sort_key("10.E", None),
        chapter_sort_key("2", 2.0),
    ]
    assert sorted(keys)[0] == chapter_sort_key("2", 2.0)
