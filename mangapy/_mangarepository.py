
from collections import namedtuple
from mangapy import downloader
import asyncio
import aiohttp
import os


class Manga:
    def __init__(self, title, chapters):
        self.title = title
        self.chapters = chapters

    @property
    def latest(self):
        return self.manga.chapters[-1]


class Chapter:
    def __init__(self, first_page_url, number):
        self.first_page_url = first_page_url
        self.number = number

    def pages(self):
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
        _pages = chapter.pages()
        for page in _pages:
            url = page.url
            tasks.append(downloader.save(session, url, to, str(page.number)))
        await asyncio.gather(*tasks)


Page = namedtuple("Page", "number url")


class MangaRepository:
    base_url = None

    def search(self, manga):
        return None










# https://github.com/techwizrd/MangaFox-Download-Script
# https://github.com/jahmad/getmanga/blob/master/getmanga/__init__.py

# brew postinstall python
# TODO:  WARNING: The script pycodestyle is installed in '/Users/alessandro/Library/Python/3.7/bin' which is not on PATH.


