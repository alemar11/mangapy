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
        chapters: list[Chapter] = []
        offset = 0
        limit = 100
        while True:
            params = {
                "manga": manga_id,
                "limit": limit,
                "offset": offset,
                "order[chapter]": "asc",
                "translatedLanguage[]": ["en"],
                "contentRating[]": ["safe", "suggestive", "erotica"],
            }
            response = self._get_session().get(f"{self.base_url}/chapter", params=params, timeout=(10, 30))
            if response.status_code != 200:
                break
            payload = response.json()
            data = payload.get("data", [])
            for item in data:
                attributes = item.get("attributes", {})
                chapter_id = attributes.get("chapter") or item.get("id")
                number = _parse_float(attributes.get("chapter"))
                volume = attributes.get("volume")
                external_url = attributes.get("externalUrl")
                translated_language = attributes.get("translatedLanguage")
                pages_count = attributes.get("pages")
                sort_key = _chapter_sort_key(volume, attributes.get("chapter"), chapter_id)
                chapter = MangadexChapter(
                    first_page_url=f"{self.base_url}/at-home/server/{item.get('id')}",
                    chapter_id=chapter_id,
                    number=number,
                    volume=volume,
                    chapter_uuid=item.get("id"),
                    external_url=external_url,
                    translated_language=translated_language,
                    pages_count=pages_count,
                    sort_key=sort_key,
                )
                chapters.append(chapter)

            total = payload.get("total", 0)
            offset += limit
            if offset >= total:
                break
        return chapters

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
    def __init__(
        self,
        first_page_url: str,
        chapter_id: str,
        number: float | None = None,
        volume: str | None = None,
        chapter_uuid: str | None = None,
        external_url: str | None = None,
        translated_language: str | None = None,
        pages_count: int | None = None,
        sort_key=None,
    ):
        super().__init__(first_page_url, chapter_id, number, sort_key=sort_key)
        self.volume = volume
        self.chapter_uuid = chapter_uuid
        self.external_url = external_url
        self.translated_language = translated_language
        self.pages_count = pages_count

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


def _parse_float(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _chapter_sort_key(volume: str | None, chapter: str | None, chapter_id: str):
    volume_number = _parse_float(volume)
    chapter_number = _parse_float(chapter)
    if chapter_number is not None:
        if volume_number is not None:
            return (0, volume_number, chapter_number, chapter_id)
        return (0, chapter_number, chapter_id)
    if volume_number is not None:
        return (1, volume_number, chapter_id)
    return (2, chapter_id)
