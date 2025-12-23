import requests
import threading

from mangapy.capabilities import ProviderCapabilities
from mangapy.mangarepository import MangaRepository, Manga, Chapter, Page


class MangadexRepository(MangaRepository):
    name = "MangaDex"
    base_url = "https://api.mangadex.org"

    def __init__(self):
        self._session_local = threading.local()

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(max_parallel_chapters=2, max_parallel_pages=4, supports_batch_download=False)

    def search(self, title) -> Manga | None:
        params = {"limit": 10, "title": title}
        response = self._get_session().get(f"{self.base_url}/manga", params=params, timeout=(10, 30))
        if response.status_code != 200:
            return None
        payload = response.json()
        results = payload.get("data", [])
        if not results:
            return None

        normalized_query = _normalize_title(title)
        best = None
        for item in results:
            attributes = item.get("attributes", {})
            if _title_matches(attributes, normalized_query):
                best = item
                break
        if best is None:
            best = results[0]

        attributes = best.get("attributes", {})
        manga_title = _pick_title(attributes) or title
        manga_id = best.get("id")
        chapters = self._fetch_chapters(manga_id)
        return MangadexManga(manga_id, manga_title, chapters)

    def _fetch_chapters(self, manga_id: str | None) -> list[Chapter]:
        if not manga_id:
            return []
        return []

    def _get_session(self) -> requests.Session:
        session = getattr(self._session_local, "session", None)
        if session is None:
            session = requests.Session()
            self._session_local.session = session
        return session


class MangadexManga(Manga):
    def __init__(self, manga_id: str, title: str, chapters: list[Chapter]):
        super().__init__(title, chapters)
        self.manga_id = manga_id


class MangadexChapter(Chapter):
    def __init__(self, first_page_url: str, chapter_id: str, number: float | None = None):
        super().__init__(first_page_url, chapter_id, number)

    def pages(self) -> list[Page]:
        return []


def _normalize_title(value: str) -> str:
    return "".join(ch for ch in value.lower() if ch.isalnum())


def _pick_title(attributes: dict) -> str | None:
    title = attributes.get("title") or {}
    if "en" in title:
        return title["en"]
    if title:
        return next(iter(title.values()))
    return None


def _title_matches(attributes: dict, normalized_query: str) -> bool:
    title = attributes.get("title") or {}
    for candidate in title.values():
        if _normalize_title(candidate) == normalized_query:
            return True
    for alt in attributes.get("altTitles", []) or []:
        for candidate in alt.values():
            if _normalize_title(candidate) == normalized_query:
                return True
    return False
