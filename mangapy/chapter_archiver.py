import logging
import os
import re
import requests
import shutil
import threading
from collections.abc import Mapping
from functools import partial
from tqdm import tqdm
from PIL import Image
from urllib.parse import urlparse
from mangapy.mangarepository import Chapter, Page
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


class ChapterArchiver(object):
    def __init__(self, path: str, max_workers=1):
        self.max_workers = max_workers
        self.path = Path(path).expanduser()
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
        response = session.get(url, headers=headers, timeout=(10, 30))
        if response.status_code != 200:
            return None
        return response.content

    def _save_image(self, image_path: Path, headers: Mapping[str, str | bytes | None] | None, page: Page):
        file_name = str(page.number)
        image_url = page.url
        file_ext = urlparse(image_url).path.split('.')[-1]
        file_path = image_path.joinpath(file_name + '.' + file_ext)
        if os.path.isfile(file_path):
            return  # early exit if the file is already on disk

        if image_url.startswith('//'):
            image_url = 'http:' + image_url

        data = self._fetch_image(image_url, headers=headers)

        if data is None:
            logging.error("Can't download page {0}".format(file_name))
            return

        output = open(file_path, "wb")
        output.write(data)
        output.close()

    def _create_chapter_pdf(self, chapter_images_path: Path, pdf_path: Path):
        file_list = list(chapter_images_path.glob('**/*'))  # we don't care of their ext
        chapter_images_path = list(map(lambda path: str(path.absolute()), file_list))
        images_path = natural_sort(chapter_images_path)

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
        tmp_path = pdf_path.with_name(pdf_path.name + ".tmp")
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
        images_path = self.path.joinpath('.images' if pdf else 'images')
        chapter_images_path = images_path.joinpath(chapter_name)
        chapter_images_path.mkdir(parents=True, exist_ok=True)
        pages = chapter.pages()
        if pages is None or not len(pages):
            print("🆘  {0} doesn't have any pages and it will be skipped.".format(chapter_name))
            return

        description = ('Chapter {0}'.format(chapter_name))
        func = partial(self._save_image, chapter_images_path, headers)  # currying

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            for _ in tqdm(executor.map(func, pages), total=len(pages), desc=description, unit='pages', ncols=100):
                pass


def natural_sort(list):
    def convert(text):
        return int(text) if text.isdigit() else text.lower()

    def alphanum_key(key):
        return [convert(c) for c in re.split('([0-9]+)', key)]

    return sorted(list, key=alphanum_key)
