import requests

from mangapy.mangadex import MangadexChapter, MangadexRepository


def _latest_en_chapter():
    url = "https://api.mangadex.org/chapter"
    params = {"translatedLanguage[]": ["en"], "order[readableAt]": "desc", "limit": 1}
    response = requests.get(url, params=params, timeout=(10, 30))
    response.raise_for_status()
    payload = response.json()
    data = payload.get("data", [])
    if not data:
        return None
    chapter = data[0]
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
