
import re
from abc import ABC, abstractmethod
from collections import namedtuple


class Manga(ABC):
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


class Chapter(ABC):
    def __init__(self, first_page_url, number):
        self.first_page_url = first_page_url
        self.number = number

    @abstractmethod
    def pages(self):
        pass


Page = namedtuple("Page", "number url")


class MangaRepository(ABC):
    base_url = None

    @abstractmethod
    def search(self, title):
        pass
