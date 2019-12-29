import context
import pytest
from mangapy.mangapark import MangaParkRepository


@pytest.mark.filterwarnings('ignore::urllib3.exceptions.InsecureRequestWarning')
def test_fetch_not_existing_manga():
    repository = MangaParkRepository()
    manga = repository.search('this manga doesn\'t exists')
    assert manga is None


@pytest.mark.filterwarnings('ignore::urllib3.exceptions.InsecureRequestWarning')
def test_fetch_manga():
    repository = MangaParkRepository()
    manga = repository.search('naruto')
    assert manga is not None
    assert len(manga.chapters) == 701, "It should contain 701 chapters"
    firstChapter = manga.chapters[0]
    assert firstChapter is not None
    pages = firstChapter.pages()
    first_chapter_count = 0
    for page in pages:
        first_chapter_count += 1
        assert page.number is not None
        assert page.url is not None
    assert first_chapter_count == 46, "The first Naruto chapter sould contain 46 pages"

    lastChapter = manga.chapters[-1]
    assert lastChapter is not None
    pages = lastChapter.pages()
    last_chapter_count = 0
    for page in pages:
        last_chapter_count += 1
        assert page.number is not None
        assert page.url is not None
    assert last_chapter_count == 18, "The last Naruto chapter sould contain 18 pages"


@pytest.mark.filterwarnings('ignore::urllib3.exceptions.InsecureRequestWarning')
def test_fetch_mangapark_adult_content():
    repository = MangaParkRepository()
    manga = repository.search('emergence')
    assert manga is not None
    assert len(manga.chapters) == 7, "It should contain 7 chapters"
    firstChapter = manga.chapters[0]
    assert firstChapter
    pages = firstChapter.pages()
    for page in pages:
        assert page.number is not None
        assert page.url is not None


@pytest.mark.filterwarnings('ignore::urllib3.exceptions.InsecureRequestWarning')
def test_fetch_mangapark_adult_content_with_single_volume():
    repository = MangaParkRepository()
    manga = repository.search('Naruto - Eroi no Vol.1 (Doujinshi)')
    assert manga is not None
    assert len(manga.chapters) == 1, "It should contain only 1 chapter"
    firstChapter = manga.chapters[0]
    assert firstChapter is not None
    pages = firstChapter.pages()
    for page in pages:
        assert page.number is not None
        assert page.url is not None
