import math
import threading
import time

import requests

from mangapy.capabilities import ProviderCapabilities
from mangapy.mangarepository import Chapter, Manga, MangaRepository, Page
from mangapy.pathutils import sanitize_filename_component

MAX_RETRY_DELAY_SECONDS = 30.0


class MangadexRepository(MangaRepository):
    name = "MangaDex"
    base_url = "https://api.mangadex.org"
    proxies: dict[str, str] | None = None

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
        results = self._search_manga_results(title)
        if not results:
            return None

        normalized_query = _normalize_title(title)
        best = None
        partial_matches = []
        for item in results:
            attributes = item.get("attributes", {})
            if _title_matches(attributes, normalized_query):
                best = item
                break
            if _title_partially_matches(attributes, normalized_query):
                partial_matches.append(item)
        if best is None:
            if not partial_matches:
                return None
            best = partial_matches[0]

        attributes = best.get("attributes", {})
        manga_title = _pick_title(attributes) or title
        manga_id = best.get("id")
        chapters = self._fetch_chapters(manga_id, translated_language, content_rating, data_saver)
        return MangadexManga(manga_id, manga_title, chapters)

    def suggestions(self, title: str, options: dict | None = None) -> list[str]:
        suggestions = []
        for item in self._search_manga_results(title)[:5]:
            suggestion = _pick_title(item.get("attributes", {}))
            if suggestion:
                suggestions.append(suggestion)
        return suggestions

    def _search_manga_results(self, title: str) -> list[dict]:
        params = {"limit": 10, "title": title}
        payload = self._request_json(f"{self.base_url}/manga", params=params)
        if payload is None:
            return []
        return payload.get("data", [])

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
        requested_languages = list(translated_language)
        expected_total: int | None = None
        seen_chapter_uuids: set[str] = set()
        while True:
            params = {
                "manga": manga_id,
                "limit": limit,
                "offset": offset,
                "order[chapter]": "asc",
                "translatedLanguage[]": requested_languages,
                "contentRating[]": content_rating,
            }
            payload = self._request_json(f"{self.base_url}/chapter", params=params)
            if payload is None:
                raise RuntimeError(f"MangaDex chapter feed failed at offset {offset}; refusing partial results")
            if not isinstance(payload, dict):
                raise RuntimeError(f"MangaDex chapter feed returned an invalid payload at offset {offset}")
            data = payload.get("data", [])
            if not isinstance(data, list):
                raise RuntimeError(f"MangaDex chapter feed returned invalid data at offset {offset}")
            for item in data:
                attributes = item.get("attributes", {})
                chapter_uuid = item.get("id")
                if not isinstance(chapter_uuid, str) or not chapter_uuid:
                    raise RuntimeError(f"MangaDex chapter feed returned an item without an id at offset {offset}")
                if chapter_uuid in seen_chapter_uuids:
                    raise RuntimeError(f"MangaDex chapter feed returned duplicate id {chapter_uuid!r}")
                seen_chapter_uuids.add(chapter_uuid)
                chapter_id = attributes.get("chapter") or item.get("id")
                number = _parse_float(attributes.get("chapter"))
                volume = attributes.get("volume")
                external_url = attributes.get("externalUrl")
                chapter_language = attributes.get("translatedLanguage")
                pages_count = attributes.get("pages")
                sort_key = _chapter_sort_key(volume, attributes.get("chapter"), chapter_id)
                chapter = MangadexChapter(
                    first_page_url=f"{self.base_url}/at-home/server/{chapter_uuid}",
                    chapter_id=chapter_id,
                    number=number,
                    volume=volume,
                    chapter_uuid=chapter_uuid,
                    external_url=external_url,
                    translated_language=chapter_language,
                    pages_count=pages_count,
                    data_saver=data_saver,
                    sort_key=sort_key,
                    requester=self._request_json,
                )
                chapters.append(chapter)

            reported_total = payload.get("total")
            if not isinstance(reported_total, int) or reported_total < 0:
                raise RuntimeError(f"MangaDex chapter feed returned an invalid total at offset {offset}")
            expected_total = max(expected_total or 0, reported_total, offset + len(data))
            if not data and offset < expected_total:
                raise RuntimeError(f"MangaDex chapter feed ended before its declared total of {expected_total}")
            offset += len(data)
            if offset >= expected_total:
                break
        _validate_unique_output_names(chapters)
        return chapters

    def _get_session(self) -> requests.Session:
        session = getattr(self._session_local, "session", None)
        if session is None:
            session = requests.Session()
            self._session_local.session = session
        session.proxies.clear()
        if self.proxies:
            session.proxies.update(self.proxies)
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
        max_attempts = 3
        response = None
        for attempt in range(max_attempts):
            self._apply_rate_limit()
            try:
                response = session.get(url, params=params, timeout=(10, 30))
            except requests.RequestException:
                if attempt < max_attempts - 1:
                    time.sleep(_retry_delay(None, attempt))
                continue
            if response.status_code == 429 or response.status_code >= 500:
                if attempt < max_attempts - 1:
                    time.sleep(_retry_delay(response, attempt))
                continue
            return response
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
        if chapter_uuid:
            # Chapter metadata can be corrected after publication. The UUID is
            # the only immutable identity suitable for an idempotent path.
            self.output_name = chapter_uuid

    def pages(self) -> list[Page]:
        if self.external_url:
            return []
        if self.pages_count == 0:
            return []
        if not self.chapter_uuid:
            return []
        if self._requester is None:
            try:
                response = requests.get(
                    self.first_page_url,
                    timeout=(10, 30),
                    headers={"Accept": "application/json", "User-Agent": "mangapy"},
                )
            except requests.RequestException:
                return []
            if response is None or response.status_code != 200:
                return []
            try:
                payload = response.json()
            except ValueError:
                return []
        else:
            try:
                payload = self._requester(self.first_page_url)
            except requests.RequestException:
                return []
        if not isinstance(payload, dict):
            return []
        if payload.get("result") != "ok":
            return []
        base_url = payload.get("baseUrl")
        chapter = payload.get("chapter", {})
        if not isinstance(chapter, dict):
            return []
        file_hash = chapter.get("hash")
        files = chapter.get("dataSaver") if self.data_saver else chapter.get("data")
        files = files or []
        if not base_url or not file_hash or not isinstance(files, list):
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


def _title_partially_matches(attributes: dict, normalized_query: str) -> bool:
    if not normalized_query:
        return False
    title = attributes.get("title") or {}
    for candidate in title.values():
        if normalized_query in _normalize_title(candidate):
            return True
    for alt in attributes.get("altTitles", []) or []:
        for candidate in alt.values():
            if normalized_query in _normalize_title(candidate):
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
        number = float(value)
    except TypeError, ValueError:
        return None
    return number if math.isfinite(number) else None


def _chapter_sort_key(volume: str | None, chapter: str | None, chapter_id: str):
    volume_number = _parse_float(volume)
    chapter_number = _parse_float(chapter)
    if chapter_number is not None:
        primary_number = volume_number if volume_number is not None else chapter_number
        return (0, primary_number, chapter_number, str(chapter_id))
    if volume_number is not None:
        return (1, volume_number, 0.0, str(chapter_id))
    return (2, 0.0, 0.0, str(chapter_id))


def _validate_unique_output_names(chapters: list[Chapter]) -> None:
    assigned_keys: set[str] = set()
    for chapter in chapters:
        candidate_key = sanitize_filename_component(chapter.output_name).casefold()
        if candidate_key in assigned_keys:
            raise RuntimeError("MangaDex chapter ids collide on the output filesystem")
        assigned_keys.add(candidate_key)


def _retry_delay(response: requests.Response | None, attempt: int) -> float:
    if response is not None:
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                retry_after_seconds = float(retry_after)
            except ValueError:
                pass
            else:
                if math.isfinite(retry_after_seconds) and retry_after_seconds >= 0:
                    return min(retry_after_seconds, MAX_RETRY_DELAY_SECONDS)
    return min(2**attempt, 5)
