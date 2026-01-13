import requests
import threading
import time

from mangapy.capabilities import ProviderCapabilities
from mangapy.mangarepository import MangaRepository, Manga, Chapter, Page


class MangadexRepository(MangaRepository):
    name = "MangaDex"
    base_url = "https://api.mangadex.org"

    def __init__(self):
        self._session_local = threading.local()
        self._rate_lock = threading.Lock()
        self._last_request = 0.0
        self.no_retry = False

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(max_parallel_chapters=2, max_parallel_pages=4, supports_batch_download=False, rate_limit=2.0)

    def search(self, title, options: dict | None = None) -> Manga | None:
        options = options or {}
        translated_language = _normalize_list_option(options.get("translated_language")) or ["en"]
        content_rating = _normalize_list_option(options.get("content_rating")) or ["safe", "suggestive", "erotica"]
        data_saver = bool(options.get("data_saver", False))
        params = {"limit": 10, "title": title}
        payload = self._request_json(f"{self.base_url}/manga", params=params)
        if payload is None:
            return None
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
        chapters = self._fetch_chapters(manga_id, translated_language, content_rating, data_saver)
        return MangadexManga(manga_id, manga_title, chapters)

    def _fetch_chapters(
        self,
        manga_id: str | None,
        translated_language: list[str],
        content_rating: list[str],
        data_saver: bool,
    ) -> list[Chapter]:
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
                "translatedLanguage[]": translated_language,
                "contentRating[]": content_rating,
            }
            payload = self._request_json(f"{self.base_url}/chapter", params=params)
            if payload is None:
                break
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
                    data_saver=data_saver,
                    sort_key=sort_key,
                    requester=self._request_json,
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

    def _request_json(self, url: str, params: dict | None = None) -> dict | None:
        response = self._request(url, params=params)
        if response is None or response.status_code != 200:
            return None
        try:
            return response.json()
        except ValueError:
            return None

    def _request(self, url: str, params: dict | None = None) -> requests.Response | None:
        session = self._get_session()
        if self.no_retry:
            self._apply_rate_limit()
            try:
                return session.get(url, params=params, timeout=(10, 30))
            except requests.RequestException:
                return None
        last_error = None
        for attempt in range(3):
            self._apply_rate_limit()
            try:
                response = session.get(url, params=params, timeout=(10, 30))
            except requests.RequestException as exc:
                last_error = exc
                delay = _retry_delay(None, attempt)
                time.sleep(delay)
                continue
            if response.status_code == 429 or response.status_code >= 500:
                delay = _retry_delay(response, attempt)
                time.sleep(delay)
                continue
            return response
        if last_error:
            return None
        return response

    def _apply_rate_limit(self) -> None:
        rate_limit = self.capabilities.rate_limit
        if not rate_limit:
            return
        min_interval = 1.0 / rate_limit
        with self._rate_lock:
            now = time.monotonic()
            elapsed = now - self._last_request
            if elapsed < min_interval:
                time.sleep(min_interval - elapsed)
            self._last_request = time.monotonic()


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
        data_saver: bool = False,
        requester=None,
        sort_key=None,
    ):
        super().__init__(first_page_url, chapter_id, number, sort_key=sort_key)
        self.volume = volume
        self.chapter_uuid = chapter_uuid
        self.external_url = external_url
        self.translated_language = translated_language
        self.pages_count = pages_count
        self.data_saver = data_saver
        self._requester = requester

    def pages(self) -> list[Page]:
        if self.external_url:
            return []
        if not self.chapter_uuid:
            return []
        if self._requester is None:
            response = requests.get(
                self.first_page_url,
                timeout=(10, 30),
                headers={"Accept": "application/json", "User-Agent": "mangapy"},
            )
            if response.status_code != 200:
                return []
            payload = response.json()
        else:
            payload = self._requester(self.first_page_url)
        if payload is None:
            return []
        if payload.get("result") != "ok":
            return []
        base_url = payload.get("baseUrl")
        chapter = payload.get("chapter", {})
        file_hash = chapter.get("hash")
        files = chapter.get("dataSaver") if self.data_saver else chapter.get("data")
        files = files or []
        if not base_url or not file_hash:
            return []
        pages = []
        for i, filename in enumerate(files):
            if self.data_saver:
                url = f"{base_url}/data-saver/{file_hash}/{filename}"
            else:
                url = f"{base_url}/data/{file_hash}/{filename}"
            pages.append(Page(i, url))
        return pages


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


def _normalize_list_option(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if item]
    return [str(value)]


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


def _retry_delay(response: requests.Response | None, attempt: int) -> float:
    if response is not None:
        retry_after = response.headers.get("Retry-After")
        if retry_after and retry_after.isdigit():
            return float(retry_after)
    return min(2 ** attempt, 5)
