import hashlib
import math
import re
import unicodedata
from abc import ABC, abstractmethod
from typing import List

from mangapy.capabilities import ProviderCapabilities
from mangapy.pathutils import sanitize_filename_component


class Page:
    def __init__(self, number: int, url: str):
        self.number = number
        self.url = url


class Chapter(ABC):
    def __init__(
        self,
        first_page_url: str,
        chapter_id: str,
        number: float | None = None,
        sort_key=None,
        output_name: str | None = None,
    ):
        self.first_page_url = first_page_url
        self.chapter_id = chapter_id
        self.number = number
        self.sort_key = sort_key if sort_key is not None else chapter_sort_key(chapter_id, number)
        self.output_name = output_name if output_name is not None else _default_chapter_output_name(chapter_id, number)

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
    def last_downloadable_chapter(self) -> Chapter | None:
        downloadable = [
            chapter
            for chapter in self.chapters
            if not getattr(chapter, "external_url", None) and getattr(chapter, "pages_count", None) != 0
        ]
        numeric = [chapter for chapter in downloadable if _is_finite_number(chapter.number)]
        if numeric:
            return max(numeric, key=lambda chapter: float(chapter.number))
        if downloadable:
            return downloadable[-1]
        return None

    @property
    def subdirectory(self):
        # subdirectory where chapters should be saved
        normalized_title = unicodedata.normalize("NFKC", str(self.title)).casefold()
        slug = re.sub(r"[^\w]+", "_", normalized_title, flags=re.UNICODE).strip("_")
        if slug and any(character.isalnum() for character in slug):
            return sanitize_filename_component(slug, fallback="manga")
        digest = hashlib.sha256(normalized_title.encode("utf-8")).hexdigest()[:12]
        return f"manga_{digest}"


class MangaRepository(ABC):
    base_url = None

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities()

    def image_request_headers(self) -> dict[str, str] | None:
        return None

    def suggestions(self, title: str, options: dict | None = None) -> list[str]:
        return []

    @abstractmethod
    def search(self, title, options: dict | None = None) -> List[Manga] | Manga | None:
        pass


def chapter_sort_key(chapter_id: str, number: float | None):
    normalized_id = str(chapter_id)
    if not _is_finite_number(number):
        return (1, 0.0, normalized_id)
    return (0, float(number), normalized_id)


def _default_chapter_output_name(chapter_id: str, number: float | None) -> str:
    if not _is_finite_number(number):
        return str(chapter_id) if chapter_id is not None else "unknown"
    numeric_value = float(number)
    if numeric_value.is_integer():
        return str(int(numeric_value))
    return str(number)


def _is_finite_number(value: float | None) -> bool:
    if value is None:
        return False
    try:
        return math.isfinite(float(value))
    except TypeError, ValueError:
        return False
