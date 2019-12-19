import context
import asyncio

from mangapy.mangapark import MangaParkRepository


def test_parse_not_existing_manga():
    repository = MangaParkRepository()
    manga = asyncio.run(repository.search('this manga doesn\'t exists'))
    assert manga is None


def test_parse_manga():
    repository = MangaParkRepository()
    manga = asyncio.run(repository.search('naruto'))
    assert manga is not None
    assert len(manga.chapters) == 701, "It should contain 701 chapters"
    firstChapter = manga.chapters[0]
    assert firstChapter is not None
    pages = asyncio.run(firstChapter.pages())
    first_chapter_count = 0
    for page in pages:
        first_chapter_count += 1
        assert page.number is not None
        assert page.url is not None
    assert first_chapter_count == 46, "The first Naruto chapter sould contain 46 pages"

    lastChapter = manga.chapters[-1]
    assert lastChapter is not None
    pages = asyncio.run(lastChapter.pages())
    last_chapter_count = 0
    for page in pages:
        last_chapter_count += 1
        assert page.number is not None
        assert page.url is not None
    assert last_chapter_count == 18, "The last Naruto chapter sould contain 18 pages"


def test_parse_mangapark_adult_content():
    repository = MangaParkRepository()
    manga = asyncio.run(repository.search('emergence'))
    assert manga is not None
    assert len(manga.chapters) == 7, "It should contain 7 chapters"
    firstChapter = manga.chapters[0]
    assert firstChapter
    pages = asyncio.run(firstChapter.pages())
    for page in pages:
        assert page.number is not None
        assert page.url is not None


def test_parse_mangapark_adult_content_with_single_volume():
    repository = MangaParkRepository()
    manga = asyncio.run(repository.search('Naruto - Eroi no Vol.1 (Doujinshi)'))
    assert manga is not None
    assert len(manga.chapters) == 1, "It should contain only 1 chapter"
    firstChapter = manga.chapters[0]
    assert firstChapter is not None
    pages = asyncio.run(firstChapter.pages())
    for page in pages:
        assert page.number is not None
        assert page.url is not None
