import context  # noqa: F401
import pytest
from mangapy.fanfox import FanFoxRepository
from context import test_proxies as proxies


def test_fetch_not_existing_manga():
    repository = FanFoxRepository()
    manga = repository.search('this manga doesn\'t exists')
    assert manga is None


def test_fetch_manga():
    repository = FanFoxRepository()
    manga = repository.search('kimetsu no yaiba')
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
    assert first_chapter_count == 55, "The first chapter sould contain 55 pages"


@pytest.mark.skip(reason="It fails most of the time using Github Actions")
def test_fetch_manga_licensed():
    repository = FanFoxRepository()
    # repository.proxies = proxies
    manga = repository.search('naruto')
    assert manga is not None
    assert len(manga.chapters) == 750, "It should contain 750 chapters"
    firstChapter = manga.chapters[0]
    assert firstChapter is not None
    pages = firstChapter.pages()
    first_chapter_count = 0
    for page in pages:
        first_chapter_count += 1
        assert page.number is not None
        assert page.url is not None
    assert first_chapter_count == 47, "The first chapter sould contain 47 pages"

    lastChapter = manga.chapters[-1]
    assert lastChapter is not None
    pages = lastChapter.pages()
    last_chapter_count = 0
    for page in pages:
        last_chapter_count += 1
        assert page.number is not None
        assert page.url is not None
    assert last_chapter_count == 46, "The last chapter sould contain 46 pages"


def test_fetch_adult_content():
    repository = FanFoxRepository()
    manga = repository.search('Backstage Lovers')
    assert manga is not None
    assert len(manga.chapters) == 4, "It should contain 4 chapters"
    firstChapter = manga.chapters[0]
    assert firstChapter
    pages = firstChapter.pages()
    for page in pages:
        assert page.number is not None
        assert page.url is not None
