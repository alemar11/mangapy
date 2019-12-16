import context
import pytest

from mangapy.mangapark import MangaParkRepository

def test_parse_not_existing_manga():
    repository = MangaParkRepository()
    manga = repository.search('this manga doesn\'t exists')
    self.assertIsNone(manga)

def test_parse_manga():
    repository = MangaParkRepository()
    manga = repository.search('naruto')
    assert manga is not None
    assert len(manga.chapters) == 1021, "It should contain 1021gg chapters"
    firstChapter = manga.chapters[0]
    assert firstChapter is not None
    pages = firstChapter.pages()
    for page in pages:
        self.assertIsNotNone(page.number)
        self.assertIsNotNone(page.url)

def test_parse_mangapark_adult_content():
    repository = MangaParkRepository()
    manga = repository.search('emergence')
    assert manga is not None
    assert len(manga.chapters) == 8, "It should contain 8 chapters"
    firstChapter = manga.chapters[0]
    assert firstChapter
    pages = firstChapter.pages()
    for page in pages:
        self.assertIsNotNone(page.number)
        self.assertIsNotNone(page.url)

def test_parse_mangapark_adult_content_with_single_volume():
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