from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Iterable, List

from mangapy.chapter_archiver import ChapterArchiver
from mangapy.mangarepository import Chapter, Manga
from mangapy.providers import get_repository


@dataclass
class DownloadRequest:
    title: str
    source: str
    output: str
    pdf: bool = False
    proxy: dict | None = None
    no_retry: bool = False
    no_progress: bool = False
    enable_debug_log: bool = False
    download_all_chapters: bool = False
    download_last_chapter: bool = False
    download_single_chapter: str | None = None
    download_chapters: str | None = None
    options: dict | None = None


class DownloadManager:
    def download(self, request: DownloadRequest) -> None:
        if request.enable_debug_log:
            logging.getLogger("mangapy").setLevel(logging.DEBUG)
        else:
            logging.getLogger("mangapy").setLevel(logging.ERROR)

        repository = get_repository(request.source)
        if request.proxy:
            repository.proxies = request.proxy
        if hasattr(repository, "no_retry"):
            repository.no_retry = request.no_retry

        print(f"🔎  Searching for {request.title} in {request.source}...")
        try:
            manga = repository.search(request.title, options=request.options)
        except Exception as exc:
            logging.error(str(exc))
            return

        if manga is None or len(manga.chapters) <= 0:
            if manga is None:
                print(f"❌  Manga {request.title} doesn't exist.")
                return
            if request.source == "mangadex":
                options = request.options or {}
                languages = _normalize_option_list(options.get("translated_language"), ["en"])
                ratings = _normalize_option_list(options.get("content_rating"), ["safe", "suggestive", "erotica"])
                language_display = ", ".join(languages) if languages else "none"
                rating_display = ", ".join(ratings) if ratings else "none"
                print(
                    f"❌  {manga.title} found, but no chapters matched the requested language(s): {language_display}."
                )
                print(
                    "ℹ️  Try a different language via YAML (translated_language) or adjust content_rating: "
                    f"{rating_display}."
                )
                return
            print(f"❌  Manga {request.title} has no chapters available.")
            return

        print(f"✅  {manga.title} found")

        chapters = _select_chapters(manga, request)
        if not chapters:
            logging.error("❌  Chapter selection is empty.")
            return
        if _all_chapters_external_or_empty(chapters):
            print("⛔️  Title found, but all selected chapters are external links or have no hosted pages.")
            return

        directory = os.path.join(request.output, request.source, manga.subdirectory)
        headers = repository.image_request_headers()
        max_parallel_pages = repository.capabilities.max_parallel_pages

        print("⬇️  Download started.")
        if repository.capabilities.max_parallel_chapters > 1 and len(chapters) > 1:
            from concurrent.futures import ThreadPoolExecutor

            with ThreadPoolExecutor(max_workers=repository.capabilities.max_parallel_chapters) as executor:
                list(
                    executor.map(
                        lambda ch: _archive_chapter(
                            directory,
                            max_parallel_pages,
                            ch,
                            request.pdf,
                            headers,
                            retry_enabled=not request.no_retry,
                            show_progress=not request.no_progress,
                        ),
                        chapters,
                    )
                )
        else:
            archiver = ChapterArchiver(
                directory,
                max_workers=max_parallel_pages,
                retry_enabled=not request.no_retry,
                show_progress=not request.no_progress,
            )
            for chapter in chapters:
                _archive_with_archiver(archiver, chapter, request.pdf, headers)

        print("🎉  Download finished.")


def _archive_chapter(
    directory: str,
    max_parallel_pages: int,
    chapter: Chapter,
    pdf: bool,
    headers,
    retry_enabled: bool,
    show_progress: bool,
):
    archiver = ChapterArchiver(
        directory,
        max_workers=max_parallel_pages,
        retry_enabled=retry_enabled,
        show_progress=show_progress,
    )
    _archive_with_archiver(archiver, chapter, pdf, headers)


def _archive_with_archiver(archiver: ChapterArchiver, chapter: Chapter, pdf: bool, headers):
    try:
        archiver.archive(chapter, pdf, headers)
    except Exception as exc:
        logging.error(str(exc))


def _select_chapters(manga: Manga, request: DownloadRequest) -> List[Chapter]:
    if request.download_all_chapters:
        return list(manga.chapters)

    if request.download_single_chapter is not None:
        value = request.download_single_chapter.strip()
        number = _parse_number(value)
        for chapter in manga.chapters:
            if number is not None and chapter.number == number:
                return [chapter]
            if chapter.chapter_id == value:
                return [chapter]
        logging.error("❌  Chapter doesn't exist.")
        return []

    if request.download_chapters is not None:
        try:
            begin, end = _parse_range(request.download_chapters)
        except ValueError as exc:
            logging.error(str(exc))
            return []
        if begin is None:
            logging.error("❌  Invalid chapter range.")
            return []
        selected: List[Chapter] = []
        for chapter in manga.chapters:
            if chapter.number is None:
                continue
            if chapter.number < begin:
                continue
            if end is not None and chapter.number > end:
                continue
            selected.append(chapter)
        return selected

    return [manga.last_chapter]


def _parse_range(value: str) -> tuple[float | None, float | None]:
    parts = value.split("-")
    if len(parts) != 2:
        return None, None
    begin = _parse_number(parts[0])
    end = _parse_number(parts[1]) if parts[1] else None
    if begin is not None and end is not None and begin > end:
        raise ValueError("invalid chapter interval, the end should be bigger than start")
    return begin, end


def _parse_number(value: str) -> float | None:
    try:
        return float(value.strip())
    except ValueError:
        return None


def _normalize_option_list(value, default: list[str]) -> list[str]:
    if value is None:
        return list(default)
    if isinstance(value, list):
        return [str(item) for item in value if item]
    return [str(value)]


def _all_chapters_external_or_empty(chapters: Iterable[Chapter]) -> bool:
    for chapter in chapters:
        external_url = getattr(chapter, "external_url", None)
        if external_url:
            continue
        pages_count = getattr(chapter, "pages_count", None)
        if pages_count == 0:
            continue
        return False
    return True
