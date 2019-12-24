
from collections import namedtuple
import re


class Manga:
    def __init__(self, title, chapters):
        self.title = title
        self.chapters = chapters

    @property
    def latest(self):
        # latest chapter available
        return self.chapters[-1]

    @property
    def subdirectory(self):
        # subdirectory where chapter should be saved
        return re.sub(r'[^A-Za-z0-9]+', '_', re.sub(r'^[^A-Za-z0-9]+|[^A-Za-z0-9]+$', '', self.title)).lower()


class Chapter:
    def __init__(self, first_page_url, number):
        self.first_page_url = first_page_url
        self.number = number

    def pages(self):
        # chapter pages
        raise Exception('pages should be implemented in a subclass')


Page = namedtuple("Page", "number url")


class MangaRepository:
    base_url = None

    def search(self, title):
        # search for a mange with the given title
        return None