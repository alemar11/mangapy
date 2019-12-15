
from collections import OrderedDict, namedtuple


class Manga:
    def __init__(self, title, chapters):
        self.title = title
        self.chapters = chapters


class Chapter:
    def __init__(self, first_page_url, number):
        self.first_page_url = first_page_url
        self.number = number

    def pages(self):
        return Page("test name", "test url")


Page = namedtuple("Page", "number url")


class MangaRepository:
    base_url = None

    def search(self, manga):
        print(manga)

# https://github.com/techwizrd/MangaFox-Download-Script
# https://github.com/jahmad/getmanga/blob/master/getmanga/__init__.py

# brew postinstall python
# TODO:  WARNING: The script pycodestyle is installed in '/Users/alessandro/Library/Python/3.7/bin' which is not on PATH.


