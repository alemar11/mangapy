
import re
from abc import ABC, abstractmethod


class Manga(ABC):
    def __init__(self, title, chapters):
        self.title = title
        self.chapters = chapters

    @property
    def last_chapter(self):
        # latest chapter available
        return self.chapters[-1]

    @property
    def subdirectory(self):
        # subdirectory where chapters should be saved
        return re.sub(r'[^A-Za-z0-9]+', '_', re.sub(r'^[^A-Za-z0-9]+|[^A-Za-z0-9]+$', '', self.title)).lower()


class Page():
    def __init__(self, number: int, url: str):
        self.number = number
        self.url = url


class Chapter(ABC):
    def __init__(self, first_page_url: str, number: float):
        self.first_page_url = first_page_url
        self.number = number

    @abstractmethod
    def pages(self) -> [Page]:
        pass


class MangaRepository(ABC):
    base_url = None

    @abstractmethod
    def search(self, title) -> [Manga]:
        pass
