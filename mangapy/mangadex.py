import requests

from mangapy.capabilities import ProviderCapabilities
from mangapy.mangarepository import MangaRepository, Manga, Chapter, Page


class MangadexRepository(MangaRepository):
    name = "MangaDex"
    base_url = "https://api.mangadex.org"

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(max_parallel_chapters=2, max_parallel_pages=4, supports_batch_download=False)

    def search(self, title) -> Manga | None:
        # Placeholder implementation; will be filled in subsequent steps.
        return None


class MangadexChapter(Chapter):
    def __init__(self, first_page_url: str, chapter_id: str, number: float | None = None):
        super().__init__(first_page_url, chapter_id, number)

    def pages(self) -> list[Page]:
        return []
