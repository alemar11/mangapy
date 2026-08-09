import pytest
import requests

from mangapy.mangadex import MAX_RETRY_DELAY_SECONDS, MangadexChapter, MangadexRepository, _retry_delay


def _latest_en_chapter():
    url = "https://api.mangadex.org/chapter"
    params = {"translatedLanguage[]": ["en"], "order[readableAt]": "desc", "limit": 10}
    response = requests.get(url, params=params, timeout=(10, 30))
    response.raise_for_status()
    payload = response.json()
    data = payload.get("data", [])
    if not data:
        return None
    chapter = None
    for candidate in data:
        attributes = candidate.get("attributes", {})
        if attributes.get("externalUrl"):
            continue
        if (attributes.get("pages") or 0) <= 0:
            continue
        chapter = candidate
        break
    if chapter is None:
        return None
    manga_id = None
    for rel in chapter.get("relationships", []):
        if rel.get("type") == "manga":
            manga_id = rel.get("id")
            break
    return chapter.get("id"), manga_id


def _manga_title(manga_id: str) -> str | None:
    url = f"https://api.mangadex.org/manga/{manga_id}"
    response = requests.get(url, timeout=(10, 30))
    response.raise_for_status()
    payload = response.json()
    attributes = payload.get("data", {}).get("attributes", {})
    title = attributes.get("title", {})
    if "en" in title:
        return title["en"]
    if title:
        return next(iter(title.values()))
    return None


@pytest.mark.live
def test_fetch_manga():
    latest = _latest_en_chapter()
    assert latest is not None
    _, manga_id = latest
    assert manga_id is not None
    title = _manga_title(manga_id)
    assert title is not None

    repo = MangadexRepository()
    manga = repo.search(title)
    assert manga is not None
    assert len(manga.chapters) > 0


@pytest.mark.live
def test_fetch_manga_chapter_pages():
    latest = _latest_en_chapter()
    assert latest is not None
    chapter_id, _ = latest
    chapter = MangadexChapter(
        first_page_url=f"https://api.mangadex.org/at-home/server/{chapter_id}",
        chapter_id=chapter_id,
        number=None,
        chapter_uuid=chapter_id,
    )
    pages = chapter.pages()
    assert pages
    assert pages[0].url.startswith("https://")


def test_mangadex_suggestions_use_search_titles(monkeypatch):
    repo = MangadexRepository()

    def fake_request_json(url, params=None):
        return {
            "data": [
                {"attributes": {"title": {"en": "One Piece"}}},
                {"attributes": {"title": {"ja-ro": "One Punch-Man"}}},
            ]
        }

    monkeypatch.setattr(repo, "_request_json", fake_request_json)

    assert repo.suggestions("one") == ["One Piece", "One Punch-Man"]


def test_mangadex_search_returns_partial_title_match(monkeypatch):
    repo = MangadexRepository()

    def fake_request_json(url, params=None):
        return {
            "data": [
                {
                    "id": "manga-1",
                    "attributes": {
                        "title": {"en": "One Piece"},
                        "altTitles": [{"en": "Wan Pisu"}],
                    },
                }
            ]
        }

    monkeypatch.setattr(repo, "_request_json", fake_request_json)
    monkeypatch.setattr(repo, "_fetch_chapters", lambda *args: [])

    manga = repo.search("one")

    assert manga is not None
    assert manga.title == "One Piece"


def test_mangadex_search_returns_none_without_title_match(monkeypatch):
    repo = MangadexRepository()

    def fake_request_json(url, params=None):
        return {
            "data": [
                {
                    "id": "manga-1",
                    "attributes": {"title": {"en": "One Piece"}},
                }
            ]
        }

    monkeypatch.setattr(repo, "_request_json", fake_request_json)

    assert repo.search("zzzzzz") is None


def _chapter_item(chapter_uuid: str, chapter: str, language: str = "en", **attributes):
    return {
        "id": chapter_uuid,
        "attributes": {
            "chapter": chapter,
            "translatedLanguage": language,
            "pages": 1,
            **attributes,
        },
    }


def test_mangadex_pagination_keeps_all_requested_languages(monkeypatch):
    repo = MangadexRepository()
    requested_languages = []
    first_page = [_chapter_item(f"uuid-{index}", str(index + 1), "it" if index == 99 else "en") for index in range(100)]
    second_page = [_chapter_item("uuid-100", "101", "en")]

    def fake_request_json(url, params=None):
        requested_languages.append(list(params["translatedLanguage[]"]))
        if params["offset"] == 0:
            return {"data": first_page, "total": 101}
        if params["offset"] == 100:
            return {"data": second_page, "total": 101}
        raise AssertionError(f"unexpected offset: {params['offset']}")

    monkeypatch.setattr(repo, "_request_json", fake_request_json)

    chapters = repo._fetch_chapters("manga-1", ["en", "it"], ["safe"], False)

    assert len(chapters) == 101
    assert requested_languages == [["en", "it"], ["en", "it"]]


def test_mangadex_pagination_rejects_partial_results(monkeypatch):
    repo = MangadexRepository()
    first_page = [_chapter_item(f"uuid-{index}", str(index + 1)) for index in range(100)]

    def fake_request_json(url, params=None):
        if params["offset"] == 0:
            return {"data": first_page, "total": 101}
        return None

    monkeypatch.setattr(repo, "_request_json", fake_request_json)

    with pytest.raises(RuntimeError, match="refusing partial results"):
        repo._fetch_chapters("manga-1", ["en"], ["safe"], False)


def test_mangadex_pagination_rejects_an_initial_feed_failure(monkeypatch):
    repo = MangadexRepository()
    monkeypatch.setattr(repo, "_request_json", lambda url, params=None: None)

    with pytest.raises(RuntimeError, match="failed at offset 0"):
        repo._fetch_chapters("manga-1", ["en"], ["safe"], False)


def test_mangadex_pagination_rejects_empty_page_before_total(monkeypatch):
    repo = MangadexRepository()
    first_page = [_chapter_item(f"uuid-{index}", str(index + 1)) for index in range(100)]

    def fake_request_json(url, params=None):
        if params["offset"] == 0:
            return {"data": first_page, "total": 101}
        return {"data": [], "total": 101}

    monkeypatch.setattr(repo, "_request_json", fake_request_json)

    with pytest.raises(RuntimeError, match="ended before its declared total"):
        repo._fetch_chapters("manga-1", ["en"], ["safe"], False)


def test_mangadex_pagination_rejects_duplicate_chapter_ids(monkeypatch):
    repo = MangadexRepository()
    feed = [
        _chapter_item("duplicate-uuid", "1"),
        _chapter_item("duplicate-uuid", "2"),
    ]
    monkeypatch.setattr(repo, "_request_json", lambda url, params=None: {"data": feed, "total": len(feed)})

    with pytest.raises(RuntimeError, match="duplicate id"):
        repo._fetch_chapters("manga-1", ["en"], ["safe"], False)


def test_mangadex_session_applies_configured_proxies():
    repo = MangadexRepository()
    session = repo._get_session()
    assert session.proxies == {}

    repo.proxies = {"http": "http://proxy.test:8080", "https": "http://proxy.test:8080"}

    assert repo._get_session() is session
    assert session.proxies == repo.proxies


def test_mangadex_output_names_always_include_stable_identity(monkeypatch):
    repo = MangadexRepository()
    feed = [
        _chapter_item("uuid-en", "1", "en"),
        _chapter_item("uuid-it", "1", "it"),
        _chapter_item("uuid-unique", "2", "en"),
    ]
    monkeypatch.setattr(repo, "_request_json", lambda url, params=None: {"data": feed, "total": len(feed)})

    chapters = repo._fetch_chapters("manga-1", ["en", "it"], ["safe"], False)

    assert [chapter.output_name for chapter in chapters] == ["uuid-en", "uuid-it", "uuid-unique"]


def test_mangadex_output_name_is_stable_when_feed_cardinality_changes(monkeypatch):
    repo = MangadexRepository()
    first_chapter = _chapter_item("uuid-first", "1", "en")
    feed = [first_chapter]

    monkeypatch.setattr(repo, "_request_json", lambda url, params=None: {"data": feed, "total": len(feed)})
    original_name = repo._fetch_chapters("manga-1", ["en"], ["safe"], False)[0].output_name

    feed = [first_chapter, _chapter_item("uuid-second", "1", "en")]
    expanded_names = [chapter.output_name for chapter in repo._fetch_chapters("manga-1", ["en"], ["safe"], False)]

    assert original_name == "uuid-first"
    assert expanded_names == ["uuid-first", "uuid-second"]


def test_mangadex_output_name_is_stable_when_metadata_changes(monkeypatch):
    repo = MangadexRepository()
    feed = [_chapter_item("uuid-stable", "1", "en")]
    monkeypatch.setattr(repo, "_request_json", lambda url, params=None: {"data": feed, "total": len(feed)})
    original_name = repo._fetch_chapters("manga-1", ["en"], ["safe"], False)[0].output_name

    feed = [_chapter_item("uuid-stable", "1.1", "it")]
    corrected_name = repo._fetch_chapters("manga-1", ["it"], ["safe"], False)[0].output_name

    assert original_name == corrected_name == "uuid-stable"


@pytest.mark.parametrize(
    ("first_name", "second_name"),
    [
        ("A/B", "A\\B"),
        ("Special", "special"),
    ],
)
def test_mangadex_rejects_ids_that_collide_on_common_filesystems(monkeypatch, first_name, second_name):
    repo = MangadexRepository()
    feed = [
        _chapter_item(first_name, "1", "en"),
        _chapter_item(second_name, "2", "it"),
    ]
    monkeypatch.setattr(repo, "_request_json", lambda url, params=None: {"data": feed, "total": len(feed)})

    with pytest.raises(RuntimeError, match="collide on the output filesystem"):
        repo._fetch_chapters("manga-1", ["en", "it"], ["safe"], False)


def test_mangadex_pages_fallback_handles_network_and_json_errors(monkeypatch):
    chapter = MangadexChapter(
        first_page_url="https://api.mangadex.org/at-home/server/uuid-1",
        chapter_id="1",
        number=1.0,
        chapter_uuid="uuid-1",
    )

    def raise_timeout(*args, **kwargs):
        raise requests.Timeout("timed out")

    monkeypatch.setattr("mangapy.mangadex.requests.get", raise_timeout)
    assert chapter.pages() == []

    class InvalidJsonResponse:
        status_code = 200

        @staticmethod
        def json():
            raise ValueError("invalid json")

    monkeypatch.setattr("mangapy.mangadex.requests.get", lambda *args, **kwargs: InvalidJsonResponse())
    assert chapter.pages() == []


def test_mangadex_retry_does_not_sleep_after_last_attempt(monkeypatch):
    repo = MangadexRepository()
    sleeps = []

    class FailingSession:
        proxies = {}

        @staticmethod
        def get(*args, **kwargs):
            raise requests.Timeout("timed out")

    repo._session_local.session = FailingSession()
    monkeypatch.setattr(repo, "_apply_rate_limit", lambda: None)
    monkeypatch.setattr("mangapy.mangadex.time.sleep", sleeps.append)

    assert repo._request("https://api.mangadex.org/manga") is None
    assert sleeps == [1, 2]


def test_mangadex_retry_after_is_capped():
    response = requests.Response()
    response.headers["Retry-After"] = "999"

    assert _retry_delay(response, attempt=0) == MAX_RETRY_DELAY_SECONDS
