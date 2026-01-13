import logging
import os
import random
import re
import sys
import requests
import shutil
import threading
import time
from collections.abc import Mapping
from functools import partial
from tqdm import tqdm
from PIL import Image
from urllib.parse import urlparse
from mangapy.mangarepository import Chapter, Page
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


tqdm.set_lock(threading.RLock())


class ChapterArchiver(object):
    def __init__(self, path: str, max_workers=1, retry_enabled: bool = True, show_progress: bool = True):
        self.max_workers = max_workers
        self.path = Path(path).expanduser()
        self.retry_enabled = retry_enabled
        self.show_progress = show_progress
        self._session_local = threading.local()
        self._pdf_lock_guard = threading.Lock()
        self._pdf_locks = {}

    def archive(self, chapter: Chapter, pdf: bool, headers: Mapping[str, str | bytes | None] | None):
        chapter_id = getattr(chapter, "chapter_id", None)
        if chapter.number is not None:
            isChapterNumberAnInt = isinstance(chapter.number, int) or chapter.number.is_integer()
            chapter_name = str(int(chapter.number)) if isChapterNumberAnInt else str(chapter.number)
        else:
            chapter_name = chapter_id if chapter_id is not None else "unknown"

        if pdf:
            pdf_path = self.path.joinpath('pdf')
            pdf_path.mkdir(parents=True, exist_ok=True)
            chapter_pdf_file_path = pdf_path.joinpath(chapter_name + '.pdf')
            lock = self._get_pdf_lock(chapter_pdf_file_path)
            with lock:
                if os.path.isfile(chapter_pdf_file_path):
                    print("⏺  {0} already downloaded and it will be skipped.".format(chapter_name))
                    return  # early exit if the file is already on disk
                self._download_chapter_images(chapter, chapter_name, headers, pdf=True)
                chapter_images_path = self.path.joinpath('.images', chapter_name)
                self._create_chapter_pdf(chapter_images_path, chapter_pdf_file_path)
                shutil.rmtree(chapter_images_path, ignore_errors=True)
        else:
            self._download_chapter_images(chapter, chapter_name, headers, pdf=False)

    def _fetch_image(self, url: str, headers: Mapping[str, str | bytes | None] | None):
        session = self._get_session()
        if not self.retry_enabled:
            try:
                response = session.get(url, headers=headers, timeout=(10, 30))
            except requests.RequestException as exc:
                logging.error("Failed to download image %s: %s", url, exc)
                return None
            if response.status_code != 200:
                return None
            return response.content

        last_error = None
        for attempt in range(3):
            try:
                response = session.get(url, headers=headers, timeout=(10, 30))
            except requests.RequestException as exc:
                last_error = exc
                time.sleep(_retry_delay(attempt))
                continue

            if response.status_code == 200:
                return response.content
            if response.status_code == 429 or response.status_code >= 500:
                time.sleep(_retry_delay(attempt, response))
                continue
            return None

        if last_error:
            logging.error("Failed to download image %s: %s", url, last_error)
        return None

    def _save_image(self, image_path: Path, headers: Mapping[str, str | bytes | None] | None, page: Page):
        file_name = str(page.number)
        image_url = page.url
        file_ext = urlparse(image_url).path.split('.')[-1]
        file_path = image_path.joinpath(file_name + '.' + file_ext)
        if os.path.isfile(file_path):
            return  # early exit if the file is already on disk

        if image_url.startswith('//'):
            image_url = 'https:' + image_url

        data = self._fetch_image(image_url, headers=headers)

        if data is None:
            logging.error("Can't download page {0}".format(file_name))
            return

        with open(file_path, "wb") as output:
            output.write(data)

    def _create_chapter_pdf(self, chapter_images_path: Path, pdf_path: Path):
        file_list = [path for path in chapter_images_path.glob('**/*') if path.is_file()]
        chapter_images_path = list(map(lambda path: str(path.absolute()), file_list))
        images_path = natural_sort(chapter_images_path)

        tmp_path = pdf_path.with_name(pdf_path.name + ".tmp")
        if _try_img2pdf(images_path, tmp_path):
            tmp_path.replace(pdf_path)
            return

        images = []
        for path in images_path:
            image = Image.open(path)
            image.load()
            if image.mode == 'RGBA':
                image = image.convert('RGB')
            images.append(image)

        images_count = len(images)
        if images_count <= 0:
            return
        first_image = images.pop(0)
        try:
            if images_count == 1:
                first_image.save(tmp_path, "PDF", resolution=100.0, save_all=True)
            else:
                first_image.save(tmp_path, "PDF", resolution=100.0, save_all=True, append_images=images)
            tmp_path.replace(pdf_path)
        finally:
            first_image.close()
            for image in images:
                image.close()
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass

    def _get_session(self) -> requests.Session:
        session = getattr(self._session_local, "session", None)
        if session is None:
            session = requests.Session()
            self._session_local.session = session
        return session

    def _get_pdf_lock(self, pdf_path: Path) -> threading.Lock:
        with self._pdf_lock_guard:
            lock = self._pdf_locks.get(pdf_path)
            if lock is None:
                lock = threading.Lock()
                self._pdf_locks[pdf_path] = lock
            return lock

    def _download_chapter_images(self, chapter: Chapter, chapter_name: str, headers, pdf: bool):
        external_url = getattr(chapter, "external_url", None)
        if external_url:
            print(f"⛔️  {chapter_name} is hosted externally and has no pages on this provider: {external_url}")
            return
        pages_count = getattr(chapter, "pages_count", None)
        if pages_count == 0:
            print(f"⛔️  {chapter_name} has no pages available on this provider.")
            return

        images_path = self.path.joinpath('.images' if pdf else 'images')
        chapter_images_path = images_path.joinpath(chapter_name)
        chapter_images_path.mkdir(parents=True, exist_ok=True)
        pages = chapter.pages()
        if pages is None or not len(pages):
            print("🆘  {0} doesn't have any pages and it will be skipped.".format(chapter_name))
            return

        description = ('Chapter {0}'.format(chapter_name))
        func = partial(self._save_image, chapter_images_path, headers)  # currying

        disable_progress = (not self.show_progress) or (not sys.stderr.isatty())
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            for _ in tqdm(
                executor.map(func, pages),
                total=len(pages),
                desc=description,
                unit='pages',
                ncols=100,
                disable=disable_progress,
            ):
                pass


def natural_sort(list):
    def convert(text):
        return int(text) if text.isdigit() else text.lower()

    def alphanum_key(key):
        return [convert(c) for c in re.split('([0-9]+)', key)]

    return sorted(list, key=alphanum_key)


def _retry_delay(attempt: int, response: requests.Response | None = None) -> float:
    if response is not None:
        retry_after = response.headers.get("Retry-After")
        if retry_after and retry_after.isdigit():
            return float(retry_after)
    base = min(2 ** attempt, 5)
    return base + random.uniform(0, 0.2)


def _try_img2pdf(image_paths: list[str], tmp_path: Path) -> bool:
    if not image_paths:
        return False
    try:
        import img2pdf
    except Exception:
        return False

    try:
        with open(tmp_path, "wb") as output:
            output.write(img2pdf.convert(image_paths, dpi=100))
        return True
    except Exception as exc:
        logging.warning("img2pdf failed, falling back to PIL: %s", exc)
        return False
