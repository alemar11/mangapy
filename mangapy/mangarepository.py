
import re
from abc import ABC, abstractmethod
from typing import List

from mangapy.capabilities import ProviderCapabilities


class Page():
    def __init__(self, number: int, url: str):
        self.number = number
        self.url = url


class Chapter(ABC):
    def __init__(self, first_page_url: str, chapter_id: str, number: float | None = None, sort_key=None):
        self.first_page_url = first_page_url
        self.chapter_id = chapter_id
        self.number = number
        self.sort_key = sort_key if sort_key is not None else chapter_sort_key(chapter_id, number)

    @abstractmethod
    def pages(self) -> List[Page]:
        pass


class Manga(ABC):
    def __init__(self, title, chapters: List[Chapter]):
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


class MangaRepository(ABC):
    base_url = None

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities()

    def image_request_headers(self) -> dict[str, str] | None:
        return None

    @abstractmethod
    def search(self, title, options: dict | None = None) -> List[Manga] | Manga | None:
        pass


def chapter_sort_key(chapter_id: str, number: float | None):
    if number is None:
        return (1, chapter_id)
    return (0, number, chapter_id)
