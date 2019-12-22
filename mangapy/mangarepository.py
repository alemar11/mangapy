
from collections import namedtuple
from mangapy import downloader
import asyncio
import aiohttp
import os
import re


class Manga:
    def __init__(self, title, chapters):
        self.title = title
        self.chapters = chapters

    @property
    def latest(self):
        # latest chapter available
        return self.chapters[-1]

    @property
    def subdirectory(self):
        # subdirectory where chapter should be saved
        return re.sub(r'[^A-Za-z0-9]+', '_', re.sub(r'^[^A-Za-z0-9]+|[^A-Za-z0-9]+$', '', self.title)).lower()


class Chapter:
    def __init__(self, first_page_url, number):
        self.first_page_url = first_page_url
        self.number = number

    def pages(self):
        # chapter pages
        raise Exception('pages should be implemented in a subclass')

    async def download(self, path):
        await download(self, path)
        '''
        async with aiohttp.ClientSession() as session:
            tasks = []
            _pages = self.pages()
            for page in _pages:
                url = page.url
                tasks.append(downloader.save(session, url, path, str(page.number)))
            contents = await asyncio.gather(*tasks)
            for content in contents:
                print(content)
        '''


async def download(chapter: Chapter, to: str):
    async with aiohttp.ClientSession() as session:
        to = os.path.join(to, str(chapter.number))
        tasks = []
        _pages = await chapter.pages()
        for page in _pages:
            url = page.url
            tasks.append(downloader.save(session, url, to, str(page.number)))
        await asyncio.gather(*tasks)
        downloader.pdf(to)

Page = namedtuple("Page", "number url")


class MangaRepository:
    base_url = None

    def search(self, title):
        # search for a mange with the given title
        return None










# https://github.com/techwizrd/MangaFox-Download-Script
# https://github.com/jahmad/getmanga/blob/master/getmanga/__init__.py

# brew postinstall python
# TODO:  WARNING: The script pycodestyle is installed in '/Users/alessandro/Library/Python/3.7/bin' which is not on PATH.


