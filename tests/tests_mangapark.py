import unittest
from context import mangapy
from mangapy.MangaPark import MangaParkRepository


class TestMangaPark(unittest.TestCase):
    repository = MangaParkRepository()

    def test_parse_not_existing_manga(self):
        manga = self.repository.search('this manga doesn\'t exists')
        self.assertIsNone(manga)

    def test_parse_manga(self):
        manga = self.repository.search('naruto')
        self.assertIsNotNone(manga)
        self.assertEqual(len(manga.chapters), 1021, "It should contain 1021gg chapters")
        firstChapter = manga.chapters[0]
        self.assertIsNotNone(firstChapter)
        pages = firstChapter.pages()
        for page in pages:
            self.assertIsNotNone(page.number)
            self.assertIsNotNone(page.url)

    def test_parse_mangapark_adult_content(self):
        manga = self.repository.search('emergence')
        self.assertIsNotNone(manga)
        self.assertEqual(len(manga.chapters), 8, "It should contain 8 chapters")
        firstChapter = manga.chapters[0]
        self.assertIsNotNone(firstChapter)
        pages = firstChapter.pages()
        for page in pages:
            self.assertIsNotNone(page.number)
            self.assertIsNotNone(page.url)

    def test_parse_mangapark_adult_content_with_single_volume(self):
        manga = self.repository.search('Naruto - Eroi no Vol.1 (Doujinshi)')
        self.assertIsNotNone(manga)
        self.assertEqual(len(manga.chapters), 1, "It should contain only 1 chapter")
        firstChapter = manga.chapters[0]
        self.assertIsNotNone(firstChapter)
        pages = firstChapter.pages()
        for page in pages:
            self.assertIsNotNone(page.number)
            self.assertIsNotNone(page.url)


if __name__ == '__main__':
    unittest.main()


# https://realpython.com/python-testing/