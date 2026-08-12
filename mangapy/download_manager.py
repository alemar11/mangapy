from __future__ import annotations

import logging
import math
import re
import stat
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from mangapy import terminal
from mangapy.chapter_archiver import ArchiveResult, ChapterArchiver
from mangapy.mangarepository import Chapter, Manga
from mangapy.pathutils import ensure_real_subdirectory
from mangapy.providers import get_repository

log = logging.getLogger("mangapy")


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
    force: bool = False


@dataclass(frozen=True)
class DownloadResult:
    selected_chapters: int = 0
    downloaded_chapters: int = 0
    existing_chapters: int = 0
    unavailable_chapters: int = 0
    failed_chapters: int = 0
    error: str | None = None

    @property
    def succeeded(self) -> bool:
        completed = self.downloaded_chapters + self.existing_chapters
        return (
            self.error is None
            and self.selected_chapters > 0
            and completed == self.selected_chapters
            and self.failed_chapters == 0
            and self.unavailable_chapters == 0
        )


class DownloadManager:
    def download(self, request: DownloadRequest) -> DownloadResult:
        _configure_logging(request.enable_debug_log)
        validation_error = _validate_request(request)
        if validation_error:
            log.error("%s", validation_error)
            return DownloadResult(error=validation_error)

        try:
            repository = get_repository(request.source)
        except ValueError as exc:
            log.error("%s", exc)
            return DownloadResult(error=str(exc))
        if request.proxy:
            repository.proxies = request.proxy
        if hasattr(repository, "no_retry"):
            repository.no_retry = request.no_retry

        log.debug("download request source=%s title=%r options=%r", request.source, request.title, request.options)
        progress = terminal.DownloadProgress(enabled=not request.no_progress)
        with progress:
            if progress.enabled:
                progress.start_search(request.title, request.source)
            else:
                terminal.info(f"Searching for {request.title} in {request.source}...", icon="⌕")

            manga = _search_manga(repository, request, progress)
            if manga is None:
                return DownloadResult(error=f"Unable to find a downloadable manga for {request.title}")

            chapters = _select_chapters(manga, request)
            if not chapters:
                message = "Chapter selection is empty"
                progress.clear_session()
                log.error("%s.", message)
                return DownloadResult(error=message)
            try:
                headers = repository.image_request_headers()
                capabilities = repository.capabilities
                _validate_capabilities(capabilities)
                manga_subdirectory = _select_manga_subdirectory(request.output, request.source, manga)
                directory = ensure_real_subdirectory(request.output, request.source, manga_subdirectory)
                archiver = ChapterArchiver(
                    str(directory),
                    max_workers=capabilities.max_parallel_pages,
                    retry_enabled=not request.no_retry,
                    force=request.force,
                    proxies=request.proxy,
                    progress=progress,
                )
            except Exception as exc:
                message = f"Unable to initialize chapter downloads: {exc}"
                progress.clear_session()
                _log_failure("%s", message)
                return DownloadResult(selected_chapters=len(chapters), error=message)

            if progress.enabled:
                progress.start_download(manga.title, request.source, len(chapters))
            else:
                terminal.success(f"Found {manga.title}.")
                terminal.info(f"Downloading {len(chapters)} chapter(s)...", icon="↓")

            def archive_chapter(chapter: Chapter) -> ArchiveResult:
                result = _archive_with_archiver(archiver, chapter, request.pdf, headers)
                progress.advance_download()
                return result

            with archiver.reuse_page_workers():
                if capabilities.max_parallel_chapters > 1 and len(chapters) > 1:
                    with ThreadPoolExecutor(max_workers=capabilities.max_parallel_chapters) as executor:
                        archive_results = list(executor.map(archive_chapter, chapters))
                else:
                    archive_results = [archive_chapter(chapter) for chapter in chapters]

            result = _summarize_archive_results(archive_results)

        provider = terminal.provider_label(request.source)
        summary = _download_summary(result)
        if result.succeeded:
            terminal.success(f"{manga.title} · {provider} — {summary}.")
        else:
            terminal.error(f"{manga.title} · {provider} — {summary}.")
        return result


def _archive_with_archiver(archiver: ChapterArchiver, chapter: Chapter, pdf: bool, headers) -> ArchiveResult:
    try:
        return archiver.archive(chapter, pdf, headers)
    except Exception as exc:
        chapter_name = str(getattr(chapter, "output_name", None) or getattr(chapter, "chapter_id", "unknown"))
        _log_failure("Failed to archive chapter %s: %s", chapter_name, exc)
        return ArchiveResult(
            chapter_name=chapter_name,
            status="failed",
            expected_pages=0,
            saved_pages=0,
            message=str(exc),
        )


def _summarize_archive_results(results: Iterable[ArchiveResult]) -> DownloadResult:
    results = list(results)
    counts = {
        "downloaded": 0,
        "already_exists": 0,
        "unavailable": 0,
        "failed": 0,
    }
    for result in results:
        if result.status in {"downloaded", "already_exists"} and not result.succeeded:
            log.error("Incomplete successful archive result for chapter %s", result.chapter_name)
            counts["failed"] += 1
        elif result.status in counts:
            counts[result.status] += 1
        else:
            log.error("Unknown archive result status %r for chapter %s", result.status, result.chapter_name)
            counts["failed"] += 1
    return DownloadResult(
        selected_chapters=len(results),
        downloaded_chapters=counts["downloaded"],
        existing_chapters=counts["already_exists"],
        unavailable_chapters=counts["unavailable"],
        failed_chapters=counts["failed"],
    )


def _search_manga(repository, request: DownloadRequest, progress: terminal.DownloadProgress) -> Manga | None:
    try:
        manga = repository.search(request.title, options=request.options)
    except Exception as exc:
        progress.clear_session()
        _log_failure("Provider search failed: %s", exc)
        return None

    if manga is None:
        progress.clear_session()
        terminal.error(f"Manga {request.title} doesn't exist.", to_stderr=False)
        _print_suggestions(repository, request.title, request.options)
        return None

    if len(manga.chapters) > 0:
        return manga

    if request.source == "mangadex":
        progress.clear_session()
        options = request.options or {}
        languages = _normalize_option_list(options.get("translated_language"), ["en"])
        ratings = _normalize_option_list(options.get("content_rating"), ["safe", "suggestive", "erotica"])
        language_display = ", ".join(languages) if languages else "none"
        rating_display = ", ".join(ratings) if ratings else "none"
        terminal.error(
            f"{manga.title} found, but no chapters matched the requested language(s): {language_display}.",
            to_stderr=False,
        )
        terminal.info(f"Try a different language via YAML (translated_language) or adjust content_rating: {rating_display}.")
        return None

    progress.clear_session()
    terminal.error(f"Manga {request.title} has no chapters available.", to_stderr=False)
    return None


def _print_suggestions(repository, title: str, options: dict | None) -> None:
    try:
        suggestions = repository.suggestions(title, options=options)
    except Exception as exc:
        log.debug("Unable to load suggestions for %r: %s", title, exc)
        return
    if not suggestions:
        return
    terminal.suggestions(suggestions)


def _select_chapters(manga: Manga, request: DownloadRequest) -> list[Chapter]:
    selector_count = sum(
        (
            bool(request.download_all_chapters),
            bool(request.download_last_chapter),
            request.download_single_chapter is not None,
            request.download_chapters is not None,
        )
    )
    if selector_count > 1:
        log.error("Chapter selection fields are mutually exclusive.")
        return []

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
        log.error("Chapter doesn't exist.")
        return []

    if request.download_chapters is not None:
        try:
            begin, end = _parse_range(request.download_chapters)
        except ValueError as exc:
            log.error(str(exc))
            return []
        if begin is None:
            log.error("Invalid chapter range.")
            return []
        selected: list[Chapter] = []
        for chapter in manga.chapters:
            chapter_number = _parse_number(chapter.number)
            if chapter_number is None:
                continue
            if chapter_number < begin:
                continue
            if end is not None and chapter_number > end:
                continue
            selected.append(chapter)
        return selected

    return _select_last_downloadable_chapter(manga)


def _select_last_downloadable_chapter(manga: Manga) -> list[Chapter]:
    chapter = manga.last_downloadable_chapter
    if chapter is None:
        log.error("No downloadable chapter is available.")
        return []
    return [chapter]


def _parse_range(value: str) -> tuple[float | None, float | None]:
    parts = value.split("-")
    if len(parts) != 2:
        return None, None
    begin = _parse_number(parts[0])
    end = _parse_number(parts[1]) if parts[1] else None
    if begin is not None and end is not None and begin > end:
        raise ValueError("invalid chapter interval, the end should be bigger than start")
    return begin, end


def _parse_number(value: object) -> float | None:
    try:
        number = float(str(value).strip())
    except TypeError, ValueError:
        return None
    return number if math.isfinite(number) else None


def _count(value: int, singular: str, status: str) -> str:
    suffix = "" if value == 1 else "s"
    return f"{value} {singular}{suffix} {status}"


def _download_summary(result: DownloadResult) -> str:
    counts = (
        (result.downloaded_chapters, "downloaded"),
        (result.existing_chapters, "already present"),
        (result.failed_chapters, "failed"),
        (result.unavailable_chapters, "unavailable"),
    )
    return ", ".join(_count(value, "chapter", status) for value, status in counts if value)


def _configure_logging(debug: bool) -> None:
    terminal.configure_logging(debug)


def _validate_request(request: DownloadRequest) -> str | None:
    for name, value in (("title", request.title), ("source", request.source), ("output", request.output)):
        if not isinstance(value, str) or not value.strip():
            return f"{name} must be a non-empty string"
    selector_count = sum(
        (
            bool(request.download_all_chapters),
            bool(request.download_last_chapter),
            request.download_single_chapter is not None,
            request.download_chapters is not None,
        )
    )
    if selector_count > 1:
        return "Chapter selection fields are mutually exclusive"
    return None


def _validate_capabilities(capabilities) -> None:
    for name in ("max_parallel_chapters", "max_parallel_pages"):
        value = getattr(capabilities, name, None)
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError(f"Provider capability {name} must be a positive integer")


def _log_failure(message: str, *args) -> None:
    if log.isEnabledFor(logging.DEBUG):
        log.exception(message, *args)
    else:
        log.error(message, *args)


def _normalize_option_list(value, default: list[str]) -> list[str]:
    if value is None:
        return list(default)
    if isinstance(value, list):
        return [str(item) for item in value if item]
    return [str(value)]


def _select_manga_subdirectory(output: str, source: str, manga: Manga) -> str:
    preferred = manga.subdirectory
    legacy = re.sub(
        r"[^A-Za-z0-9]+",
        "_",
        re.sub(r"^[^A-Za-z0-9]+|[^A-Za-z0-9]+$", "", str(manga.title)),
    ).lower()
    if not legacy or legacy == preferred:
        return preferred

    try:
        output_root = Path(output).expanduser().resolve(strict=True)
        legacy_path = output_root / source / legacy
        preferred_path = output_root / source / preferred
        metadata = legacy_path.lstat()
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            return preferred
        resolved_legacy = legacy_path.resolve(strict=True)
        if resolved_legacy != output_root and output_root not in resolved_legacy.parents:
            return preferred
        if not preferred_path.exists():
            return legacy
    except OSError:
        pass
    return preferred
