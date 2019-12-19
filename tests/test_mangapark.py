import context
import asyncio

from mangapy.mangapark import MangaParkRepository


def test_parse_not_existing_manga():
    repository = MangaParkRepository()
    manga = asyncio.run(repository.search('this manga doesn\'t exists'))
    assert manga is None


def test_parse_manga_first_chapter():
    repository = MangaParkRepository()
    manga = asyncio.run(repository.search('naruto'))
    assert manga is not None
    assert len(manga.chapters) == 1021, "It should contain 1021 chapters"
    firstChapter = manga.chapters[0]
    assert firstChapter is not None
    pages = asyncio.run(firstChapter.pages())
    count = 0
    for page in pages:
        count += 1
        assert page.number is not None
        assert page.url is not None
    assert count == 46, "The first Naruto chapter sould contain 46 pages"


def test_parse_manga_last_chapter():
    repository = MangaParkRepository()
    manga = asyncio.run(repository.search('naruto'))
    assert manga is not None
    assert len(manga.chapters) == 1021, "It should contain 1021 chapters"
    lastChapter = manga.chapters[-1]
    assert lastChapter is not None
    pages = asyncio.run(lastChapter.pages())
    count = 0
    for page in pages:
        count += 1
        assert page.number is not None
        assert page.url is not None
    assert count == 46, "The last Naruto chapter sould contain 18 pages"


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
