from __future__ import annotations

import math
import os
import random
import re
import shutil
import stat
import sys
import tempfile
import threading
import time
import unicodedata
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Literal
from urllib.parse import unquote, urlparse

import img2pdf
import pikepdf
import requests
from PIL import Image
from tqdm import tqdm

from mangapy import log, terminal
from mangapy.mangarepository import Chapter, Page
from mangapy.pathutils import sanitize_filename_component as _sanitize_filename_component

tqdm.set_lock(threading.RLock())

ArchiveStatus = Literal["downloaded", "already_exists", "unavailable", "failed"]
_PageStatus = Literal["downloaded", "already_exists", "failed"]
_MAX_RETRY_AFTER_SECONDS = 30.0
_MANAGED_IMAGE_EXTENSIONS = {
    ".avif",
    ".bmp",
    ".gif",
    ".heic",
    ".heif",
    ".img",
    ".j2k",
    ".jfif",
    ".jp2",
    ".jpe",
    ".jpeg",
    ".jpg",
    ".jpf",
    ".jpx",
    ".png",
    ".tif",
    ".tiff",
    ".webp",
}


@dataclass(frozen=True, slots=True)
class ArchiveResult:
    status: ArchiveStatus
    chapter_name: str
    expected_pages: int
    saved_pages: int
    message: str = ""

    @property
    def succeeded(self) -> bool:
        return (
            self.status in {"downloaded", "already_exists"}
            and self.expected_pages > 0
            and self.saved_pages == self.expected_pages
        )


@dataclass(frozen=True, slots=True)
class _PageResult:
    status: _PageStatus
    path: Path | None
    message: str = ""

    @property
    def succeeded(self) -> bool:
        return self.status in {"downloaded", "already_exists"}


@dataclass(frozen=True, slots=True)
class _ImageDownloadResult:
    expected_pages: int
    page_results: tuple[_PageResult, ...]
    unavailable_message: str = ""
    failure_message: str = ""

    @property
    def saved_pages(self) -> int:
        return sum(result.succeeded for result in self.page_results)

    @property
    def downloaded_pages(self) -> int:
        return sum(result.status == "downloaded" for result in self.page_results)

    @property
    def image_paths(self) -> list[Path]:
        return [result.path for result in self.page_results if result.succeeded and result.path is not None]

    @property
    def complete(self) -> bool:
        return self.expected_pages > 0 and self.saved_pages == self.expected_pages


class UnsafeOutputPathError(OSError):
    pass


class ChapterArchiver:
    def __init__(
        self,
        path: str,
        max_workers: int = 1,
        retry_enabled: bool = True,
        show_progress: bool = True,
        proxies: Mapping[str, str] | None = None,
    ):
        output_path = Path(path).expanduser()
        output_path.mkdir(parents=True, exist_ok=True)
        output_metadata = output_path.lstat()
        if stat.S_ISLNK(output_metadata.st_mode) or not stat.S_ISDIR(output_metadata.st_mode):
            raise UnsafeOutputPathError(f"Output path is not a real directory: {output_path}")
        self.path = output_path.resolve(strict=True)
        if not self.path.is_dir():
            raise NotADirectoryError(f"Output path is not a directory: {self.path}")

        self.max_workers = max_workers
        self.retry_enabled = retry_enabled
        self.show_progress = show_progress
        self.proxies = dict(proxies or {})
        self._session_local = threading.local()
        self._chapter_lock_guard = threading.Lock()
        self._chapter_locks: dict[str, threading.Lock] = {}

    def archive(
        self,
        chapter: Chapter,
        pdf: bool,
        headers: Mapping[str, str | bytes | None] | None,
    ) -> ArchiveResult:
        chapter_name = self._chapter_name(chapter)
        expected_pages = _known_pages_count(chapter)
        lock = self._get_chapter_lock(chapter_name)

        try:
            with lock:
                return self._archive_locked(chapter, chapter_name, expected_pages, pdf, headers)
        except Exception as exc:
            message = f"Failed to archive chapter {chapter_name}: {exc}"
            log.error(message)
            return ArchiveResult("failed", chapter_name, expected_pages, 0, message)

    def _archive_locked(
        self,
        chapter: Chapter,
        chapter_name: str,
        known_pages_count: int,
        pdf: bool,
        headers: Mapping[str, str | bytes | None] | None,
    ) -> ArchiveResult:
        preloaded_pages: Sequence[Page] | None = None
        pdf_file_path: Path | None = None
        if pdf:
            pdf_path = self._ensure_directory("pdf")
            pdf_file_path = self._safe_file_target(pdf_path, f"{chapter_name}.pdf")
            existing_pdf_pages = self._valid_pdf_page_count(pdf_file_path)
            existing_pdf_is_complete = existing_pdf_pages is not None and existing_pdf_pages == known_pages_count
            if existing_pdf_pages is not None and known_pages_count == 0:
                if getattr(chapter, "external_url", None) or getattr(chapter, "pages_count", None) == 0:
                    existing_pdf_is_complete = True
                else:
                    fetched_pages = chapter.pages()
                    if fetched_pages is None:
                        message = f"Could not verify the existing PDF for chapter {chapter_name}: page discovery failed."
                        log.error(message)
                        return ArchiveResult(
                            "failed",
                            chapter_name,
                            existing_pdf_pages,
                            existing_pdf_pages,
                            message,
                        )
                    preloaded_pages = fetched_pages
                    existing_pdf_is_complete = len(fetched_pages) == existing_pdf_pages and len(fetched_pages) > 0
            if existing_pdf_is_complete:
                message = f"Chapter {chapter_name} is already downloaded and will be skipped."
                terminal.muted(message)
                return ArchiveResult(
                    "already_exists",
                    chapter_name,
                    known_pages_count or existing_pdf_pages,
                    existing_pdf_pages,
                    message,
                )

        external_url = getattr(chapter, "external_url", None)
        if external_url:
            message = f"Chapter {chapter_name} is hosted externally and has no pages on this provider: {external_url}"
            terminal.warning(message, to_stderr=False)
            return ArchiveResult("unavailable", chapter_name, known_pages_count, 0, message)

        if getattr(chapter, "pages_count", None) == 0:
            message = f"Chapter {chapter_name} has no pages available on this provider."
            terminal.warning(message, to_stderr=False)
            return ArchiveResult("unavailable", chapter_name, 0, 0, message)

        image_result = self._download_chapter_images(
            chapter,
            chapter_name,
            headers,
            pdf=pdf,
            known_pages_count=known_pages_count,
            pages=preloaded_pages,
        )
        if image_result.unavailable_message:
            terminal.warning(image_result.unavailable_message, to_stderr=False)
            return ArchiveResult(
                "unavailable",
                chapter_name,
                image_result.expected_pages,
                image_result.saved_pages,
                image_result.unavailable_message,
            )

        if image_result.failure_message:
            log.error(image_result.failure_message)
            return ArchiveResult(
                "failed",
                chapter_name,
                image_result.expected_pages,
                image_result.saved_pages,
                image_result.failure_message,
            )

        if not image_result.complete:
            failed_pages = image_result.expected_pages - image_result.saved_pages
            page_messages = [result.message for result in image_result.page_results if not result.succeeded and result.message]
            details = f" ({'; '.join(page_messages)})" if page_messages else ""
            message = (
                f"Chapter {chapter_name} is incomplete: {failed_pages} of {image_result.expected_pages} pages failed{details}."
            )
            log.error(message)
            return ArchiveResult(
                "failed",
                chapter_name,
                image_result.expected_pages,
                image_result.saved_pages,
                message,
            )

        if pdf:
            assert pdf_file_path is not None
            try:
                self._create_chapter_pdf(image_result.image_paths, pdf_file_path)
            except Exception as exc:
                message = f"Failed to create PDF for chapter {chapter_name}: {exc}"
                log.error(message)
                return ArchiveResult(
                    "failed",
                    chapter_name,
                    image_result.expected_pages,
                    image_result.saved_pages,
                    message,
                )

            chapter_images_path = self._ensure_directory(".images", chapter_name)
            try:
                shutil.rmtree(chapter_images_path)
            except OSError as exc:
                log.warning("Could not remove temporary images for chapter %s: %s", chapter_name, exc)

            message = f"Downloaded chapter {chapter_name} as PDF."
            return ArchiveResult(
                "downloaded",
                chapter_name,
                image_result.expected_pages,
                image_result.saved_pages,
                message,
            )

        status: ArchiveStatus = "downloaded" if image_result.downloaded_pages else "already_exists"
        if status == "downloaded":
            message = f"Downloaded all {image_result.saved_pages} pages for chapter {chapter_name}."
        else:
            message = f"All {image_result.saved_pages} pages for chapter {chapter_name} already exist."
        return ArchiveResult(status, chapter_name, image_result.expected_pages, image_result.saved_pages, message)

    def _chapter_name(self, chapter: Chapter) -> str:
        output_name = getattr(chapter, "output_name", None)
        if output_name is not None:
            return _sanitize_filename_component(output_name)

        chapter_number = getattr(chapter, "number", None)
        if chapter_number is not None:
            if isinstance(chapter_number, int) or (isinstance(chapter_number, float) and chapter_number.is_integer()):
                return str(int(chapter_number))
            return _sanitize_filename_component(chapter_number)

        chapter_id = getattr(chapter, "chapter_id", None)
        return _sanitize_filename_component(chapter_id if chapter_id is not None else "unknown")

    def _fetch_image(self, url: str, headers: Mapping[str, str | bytes | None] | None) -> bytes | None:
        session = self._get_session()
        max_attempts = 3 if self.retry_enabled else 1
        last_error: Exception | None = None

        for attempt in range(max_attempts):
            response: requests.Response | None = None
            try:
                response = session.get(url, headers=headers, timeout=(10, 30))
            except requests.RequestException as exc:
                last_error = exc
            else:
                if response.status_code == 200 and response.content:
                    return response.content
                if response.status_code == 200:
                    last_error = ValueError("server returned an empty response body")
                elif response.status_code != 429 and response.status_code < 500:
                    return None

            if attempt < max_attempts - 1:
                time.sleep(_retry_delay(attempt, response))

        if last_error:
            log.error("Failed to download image %s: %s", url, last_error)
        return None

    def _save_image(
        self,
        image_path: Path,
        headers: Mapping[str, str | bytes | None] | None,
        page: Page,
    ) -> _PageResult:
        file_name = _sanitize_filename_component(page.number, fallback="page")
        temporary_path: Path | None = None
        try:
            image_url = page.url
            file_path = self._safe_file_target(image_path, _page_target_name(page))
            if self._is_valid_image(file_path):
                return _PageResult("already_exists", file_path)

            if image_url.startswith("//"):
                image_url = "https:" + image_url

            data = self._fetch_image(image_url, headers=headers)
            if not data:
                message = f"Can't download page {file_name}"
                log.error(message)
                return _PageResult("failed", None, message)

            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=image_path,
                prefix=f".{file_name}.",
                suffix=".tmp",
                delete=False,
            ) as output:
                temporary_path = Path(output.name)
                output.write(data)
                output.flush()
                os.fsync(output.fileno())

            if not self._is_valid_image(temporary_path):
                raise ValueError("downloaded content is not a valid image")
            self._safe_file_target(image_path, file_path.name)
            os.replace(temporary_path, file_path)
            return _PageResult("downloaded", file_path)
        except Exception as exc:
            message = f"Can't save page {file_name}: {exc}"
            log.error(message)
            return _PageResult("failed", None, message)
        finally:
            if temporary_path is not None:
                _unlink_if_exists(temporary_path)

    def _create_chapter_pdf(self, image_paths: Sequence[Path], pdf_path: Path) -> None:
        images = natural_sort([str(path.absolute()) for path in image_paths])
        if not images:
            raise ValueError("no images are available")

        try:
            pdf_data = img2pdf.convert(images, dpi=100)
        except Exception:
            self._discard_cached_images(image_paths)
            raise
        if not pdf_data:
            raise ValueError("PDF generator returned empty content")

        self._safe_file_target(pdf_path.parent, pdf_path.name)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=pdf_path.parent,
                prefix=f".{pdf_path.name}.",
                suffix=".tmp",
                delete=False,
            ) as output:
                temporary_path = Path(output.name)
                output.write(pdf_data)
                output.flush()
                os.fsync(output.fileno())

            if self._valid_pdf_page_count(temporary_path) != len(image_paths):
                raise ValueError("PDF generator returned invalid content")
            self._safe_file_target(pdf_path.parent, pdf_path.name)
            os.replace(temporary_path, pdf_path)
        finally:
            if temporary_path is not None:
                _unlink_if_exists(temporary_path)

    def _discard_cached_images(self, image_paths: Sequence[Path]) -> None:
        for image_path in image_paths:
            try:
                self._safe_file_target(image_path.parent, image_path.name)
                image_path.unlink(missing_ok=True)
            except OSError as exc:
                log.warning("Could not discard invalid cached image %s: %s", image_path, exc)

    def _get_session(self) -> requests.Session:
        session = getattr(self._session_local, "session", None)
        if session is None:
            session = requests.Session()
            session.proxies.update(self.proxies)
            self._session_local.session = session
        return session

    def _get_chapter_lock(self, chapter_name: str) -> threading.Lock:
        with self._chapter_lock_guard:
            lock = self._chapter_locks.get(chapter_name)
            if lock is None:
                lock = threading.Lock()
                self._chapter_locks[chapter_name] = lock
            return lock

    def _download_chapter_images(
        self,
        chapter: Chapter,
        chapter_name: str,
        headers: Mapping[str, str | bytes | None] | None,
        pdf: bool,
        known_pages_count: int,
        pages: Sequence[Page] | None = None,
    ) -> _ImageDownloadResult:
        if pages is None:
            pages = chapter.pages()
        if pages is None:
            message = f"Chapter {chapter_name} page discovery failed."
            return _ImageDownloadResult(known_pages_count, (), failure_message=message)
        if not len(pages):
            if known_pages_count > 0:
                message = f"Chapter {chapter_name} returned no pages, but the provider advertised {known_pages_count}."
                return _ImageDownloadResult(known_pages_count, (), failure_message=message)
            message = f"Chapter {chapter_name} doesn't have any pages and will be skipped."
            return _ImageDownloadResult(0, (), message)
        if known_pages_count > 0 and len(pages) != known_pages_count:
            message = f"Chapter {chapter_name} returned {len(pages)} pages, but the provider advertised {known_pages_count}."
            return _ImageDownloadResult(known_pages_count, (), failure_message=message)

        target_names = tuple(_page_target_name(page) for page in pages)
        target_keys = [_filesystem_name_key(name) for name in target_names]
        if len(set(target_keys)) != len(target_keys):
            message = f"Chapter {chapter_name} contains duplicate page output names."
            return _ImageDownloadResult(len(pages), (), failure_message=message)

        images_directory = ".images" if pdf else "images"
        chapter_images_path = self._ensure_directory(images_directory, chapter_name)
        description = f"Chapter {chapter_name}"
        save_page = partial(self._save_image, chapter_images_path, headers)

        disable_progress = (not self.show_progress) or (not sys.stderr.isatty())
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            page_results = tuple(
                tqdm(
                    executor.map(save_page, pages),
                    total=len(pages),
                    desc=description,
                    unit="pages",
                    ncols=100,
                    disable=disable_progress,
                )
            )

        result = _ImageDownloadResult(len(pages), page_results)
        if not pdf and result.complete:
            cleanup_error = self._remove_stale_images(chapter_images_path, result.image_paths)
            if cleanup_error:
                return _ImageDownloadResult(len(pages), page_results, failure_message=cleanup_error)
            if not all(self._is_valid_image(path) for path in result.image_paths):
                message = f"Chapter {chapter_name} image reconciliation removed or invalidated a current page."
                return _ImageDownloadResult(len(pages), page_results, failure_message=message)
        return result

    def _remove_stale_images(self, image_path: Path, expected_paths: Sequence[Path]) -> str:
        try:
            for candidate in image_path.iterdir():
                metadata = candidate.lstat()
                if not stat.S_ISREG(metadata.st_mode) or not _is_managed_page_file(candidate.name):
                    continue
                if any(_same_file(candidate, expected_path) for expected_path in expected_paths):
                    continue
                self._safe_file_target(image_path, candidate.name)
                candidate.unlink()
        except OSError as exc:
            return f"Could not reconcile stale images in {image_path.name}: {exc}"
        return ""

    def _ensure_directory(self, *parts: str) -> Path:
        current = self.path
        self._verify_directory(current)

        for part in parts:
            if not part or Path(part).name != part or part in {".", ".."}:
                raise UnsafeOutputPathError(f"Unsafe output path component: {part!r}")
            candidate = current.joinpath(part)
            try:
                candidate.mkdir()
            except FileExistsError:
                pass
            self._verify_directory(candidate)
            current = candidate

        return current

    def _verify_directory(self, path: Path) -> None:
        try:
            metadata = path.lstat()
        except FileNotFoundError as exc:
            raise UnsafeOutputPathError(f"Output directory disappeared: {path}") from exc
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            raise UnsafeOutputPathError(f"Output path is not a real directory: {path}")
        self._assert_within_root(path.resolve(strict=True))

    def _safe_file_target(self, directory: Path, file_name: str) -> Path:
        if not file_name or Path(file_name).name != file_name or file_name in {".", ".."}:
            raise UnsafeOutputPathError(f"Unsafe output filename: {file_name!r}")
        self._verify_directory(directory)
        target = directory.joinpath(file_name)
        self._assert_within_root(target)
        try:
            metadata = target.lstat()
        except FileNotFoundError:
            return target
        if stat.S_ISLNK(metadata.st_mode):
            raise UnsafeOutputPathError(f"Refusing to use symlink output: {target}")
        if not stat.S_ISREG(metadata.st_mode):
            raise UnsafeOutputPathError(f"Output target is not a regular file: {target}")
        return target

    def _assert_within_root(self, path: Path) -> None:
        if path != self.path and self.path not in path.parents:
            raise UnsafeOutputPathError(f"Output path escapes the configured root: {path}")

    def _is_nonempty_file(self, path: Path) -> bool:
        self._safe_file_target(path.parent, path.name)
        try:
            metadata = path.lstat()
        except FileNotFoundError:
            return False
        return stat.S_ISREG(metadata.st_mode) and metadata.st_size > 0

    def _is_valid_image(self, path: Path) -> bool:
        if not self._is_nonempty_file(path):
            return False
        try:
            with Image.open(path) as image:
                image.verify()
            with Image.open(path) as image:
                image.load()
        except Exception:
            return False
        return True

    def _valid_pdf_page_count(self, path: Path) -> int | None:
        if not self._is_nonempty_file(path):
            return None
        if path.stat().st_size < 12:
            return None
        with path.open("rb") as pdf_file:
            header = pdf_file.read(5)
            pdf_file.seek(max(0, path.stat().st_size - 1024))
            trailer = pdf_file.read()
        if header != b"%PDF-" or b"%%EOF" not in trailer:
            return None
        try:
            with pikepdf.open(path) as pdf:
                page_count = len(pdf.pages)
        except Exception:
            return None
        return page_count if page_count > 0 else None


def natural_sort(items: Sequence[str]) -> list[str]:
    def convert(text: str) -> int | str:
        return int(text) if text.isdigit() else text.lower()

    def alphanum_key(key: str) -> list[int | str]:
        return [convert(component) for component in re.split("([0-9]+)", key)]

    return sorted(items, key=alphanum_key)


def _known_pages_count(chapter: Chapter) -> int:
    value = getattr(chapter, "pages_count", None)
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


def _image_extension(url: str) -> str:
    suffix = Path(unquote(urlparse(url).path)).suffix.lower()
    if re.fullmatch(r"\.[a-z0-9]{1,10}", suffix):
        return suffix
    return ".img"


def _page_target_name(page: Page) -> str:
    file_name = _sanitize_filename_component(page.number, fallback="page")
    return f"{file_name}{_image_extension(page.url)}"


def _filesystem_name_key(value: str) -> str:
    return unicodedata.normalize("NFKC", value).casefold()


def _is_managed_page_file(file_name: str) -> bool:
    path = Path(file_name)
    return path.stem.isdigit() and path.suffix.lower() in _MANAGED_IMAGE_EXTENSIONS


def _same_file(first: Path, second: Path) -> bool:
    try:
        return first.samefile(second)
    except FileNotFoundError:
        return False


def _retry_delay(attempt: int, response: requests.Response | None = None) -> float:
    if response is not None:
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                delay = float(retry_after)
                if math.isfinite(delay):
                    return min(max(delay, 0.0), _MAX_RETRY_AFTER_SECONDS)
            except ValueError:
                pass
    base = min(2**attempt, 5)
    return base + random.uniform(0, 0.2)


def _unlink_if_exists(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass
    except OSError:
        log.warning("Could not remove temporary file %s", path)
