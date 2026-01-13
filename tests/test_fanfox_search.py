import pytest

from mangapy.fanfox import FanFoxRepository, FanFoxChapter


class _FakeResponse:
    def __init__(self, status_code: int, text: str):
        self.status_code = status_code
        self.text = text


class _FakeSession:
    def __init__(self, responses: dict[str, list[_FakeResponse]]):
        self._responses = {key: list(values) for key, values in responses.items()}

    def get(self, url, params=None, **kwargs):
        key = url
        if key not in self._responses:
            if "search" in url:
                key = "search"
            else:
                return _FakeResponse(404, "")
        responses = self._responses.get(key, [])
        if not responses:
            return _FakeResponse(404, "")
        return responses.pop(0)


def _search_html(titles: list[tuple[str, str]]) -> str:
    items = []
    for title, href in titles:
        items.append(
            f'<li><p class="manga-list-4-item-title">'
            f'<a href="{href}" title="{title}">{title}</a></p></li>'
        )
    items_html = "".join(items)
    return f'<ul class="manga-list-4-list line">{items_html}</ul>'


def _manga_html(chapter_ids: list[str]) -> str:
    links = []
    for chapter_id in chapter_ids:
        links.append(f'<a href="/manga/test/c{chapter_id}/1.html">Ch.{chapter_id}</a>')
    return f'<div id="list-2"><ul class="detail-main-list">{"".join(links)}</ul></div>'


def test_search_manga_exact_match():
    repo = FanFoxRepository()
    search_html = _search_html([("Gachi Akuta", "/manga/gachi_akuta/")])
    session = _FakeSession({"search": [_FakeResponse(200, search_html)]})
    repo._session_local.session = session

    match = repo._search_manga("Gachi Akuta")

    assert match == ("Gachi Akuta", "https://fanfox.net/manga/gachi_akuta/")


def test_search_manga_partial_match():
    repo = FanFoxRepository()
    search_html = _search_html([("Gachi Akuta", "/manga/gachi_akuta/")])
    session = _FakeSession({"search": [_FakeResponse(200, search_html)]})
    repo._session_local.session = session

    match = repo._search_manga("gachi")

    assert match == ("Gachi Akuta", "https://fanfox.net/manga/gachi_akuta/")


def test_search_manga_no_match_returns_none():
    repo = FanFoxRepository()
    search_html = _search_html([("One Piece", "/manga/one_piece/")])
    session = _FakeSession({"search": [_FakeResponse(200, search_html)]})
    repo._session_local.session = session

    match = repo._search_manga("this manga doesn't exist")

    assert match is None


def test_search_fallback_uses_search_results():
    repo = FanFoxRepository()
    search_html = _search_html([("Gachi Akuta", "/manga/gachi_akuta/")])
    manga_html = _manga_html(["001", "002"])
    session = _FakeSession(
        {
            "https://fanfox.net/manga/gachi_akuta/": [
                _FakeResponse(404, ""),
                _FakeResponse(200, manga_html),
            ],
            "search": [_FakeResponse(200, search_html)],
        }
    )
    repo._session_local.session = session

    manga = repo.search("Gachi Akuta")

    assert manga is not None
    assert manga.title == "Gachi Akuta"
    assert len(manga.chapters) == 2


def test_fetch_chapterfun_links_uses_imagecount(monkeypatch):
    chapter = FanFoxChapter("https://fanfox.net/manga/test/c001/1.html", "001", 1.0, lambda: None)
    calls = []

    def fake_one_link_helper(page, base_url, cid, key):
        calls.append(page)
        return f"data-{page}"

    def fake_get_urls(content):
        return content

    def fake_parse_links(data):
        return [f"url-{data}"]

    monkeypatch.setattr(chapter, "_one_link_helper", fake_one_link_helper)
    monkeypatch.setattr(chapter, "_get_urls", fake_get_urls)
    monkeypatch.setattr(chapter, "_parse_links", fake_parse_links)

    links = chapter._fetch_chapterfun_links("https://fanfox.net/manga/test/c001", "123", 5, "")

    assert calls == [1, 3, 5]
    assert links == ["url-data-1", "url-data-3", "url-data-5"]
