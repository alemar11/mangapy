import context  # noqa: F401
import pytest

from mangapy.fanfox import FanFoxRepository

pytestmark = pytest.mark.live


def test_fanfox_fetch_not_existing_manga():
    repository = FanFoxRepository()
    manga = repository.search("this manga doesn't exists")
    assert manga is None


def test_fetch_manga_chapter_pages():
    repository = FanFoxRepository()
    manga = repository.search("ahiru no sora")
    assert manga is not None
    assert len(manga.chapters) >= 165, "It should contain at least 165 chapters (expected more)"
    chapter = next((chapter for chapter in manga.chapters if chapter.number == 164.0), None)
    assert chapter is not None
    print(chapter.number)
    pages = chapter.pages()
    chapter_count = 0
    for page in pages:
        chapter_count += 1
        assert page.number is not None
        assert page.url is not None
    assert chapter_count == 18, "The chapter should contain 18 pages"


def test_fetch_manga():
    repository = FanFoxRepository()
    manga = repository.search("kimetsu no yaiba")
    assert manga is not None
    assert len(manga.chapters) >= 209, "It should contain at least 209 chapters"
    firstChapter = manga.chapters[0]
    assert firstChapter is not None
    pages = firstChapter.pages()
    first_chapter_count = 0
    for page in pages:
        first_chapter_count += 1
        assert page.number is not None
        assert page.url is not None
    assert first_chapter_count == 56, "The first chapter should contain 56 pages"


def test_fanfox_fetch_manga_with_missing_extra_chapters():
    # Chapters numbered "87.E" and "87.Extra" that gets skipped by the engine
    repository = FanFoxRepository()
    manga = repository.search("tower of god")
    assert manga is not None
    assert len(manga.chapters) >= 600, "It should contain more than chapters"
    chapter = manga.chapters[87]
    assert chapter is not None
    pages = chapter.pages()
    chapter_count = 0
    for page in pages:
        chapter_count += 1
        assert page.number is not None
        assert page.url is not None
    assert chapter_count == 31, "The chapter should contain 31 pages"


def test_fanfox_fetch_completed_manga():
    repository = FanFoxRepository()
    manga = repository.search("Boku dake ga Inai Machi")
    assert manga is not None
    assert len(manga.chapters) == 44
    first_chapter, last_chapter = manga.chapters[0], manga.chapters[-1]
    assert first_chapter.number == 1
    assert last_chapter.number == 44

    for chapter, expected_pages in ((first_chapter, 43), (last_chapter, 50)):
        pages = list(chapter.pages())
        assert len(pages) == expected_pages
        for page in pages:
            assert page.number is not None
            assert page.url is not None


def test_fanfox_fetch_adult_content():
    repository = FanFoxRepository()
    manga = repository.search("Backstage Lovers")
    assert manga is not None
    assert len(manga.chapters) == 4, "It should contain 4 chapters"
    firstChapter = manga.chapters[0]
    assert firstChapter
    pages = firstChapter.pages()
    for page in pages:
        assert page.number is not None
        assert page.url is not None
