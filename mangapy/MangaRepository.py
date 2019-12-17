
from collections import namedtuple
import downloader
import asyncio
import aiohttp
import hashlib

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

    def download(self, path):
        loop = asyncio.get_event_loop()
        loop.run_until_complete(self.fetch(path))

    async def fetch(self, path):
        tasks = []
        async with aiohttp.ClientSession() as session:
            for page in self.pages():
                url = page.url
                hash_object = hashlib.md5(url.encode())
                digest = hash_object.hexdigest()
                tasks.append(downloader.save(session, url, path, str(page.number)))
            contents = await asyncio.gather(*tasks)
            for content in contents:
                print(content)    



Page = namedtuple("Page", "number url")


class MangaRepository:
    base_url = None

    def search(self, manga):
        return None










# https://github.com/techwizrd/MangaFox-Download-Script
# https://github.com/jahmad/getmanga/blob/master/getmanga/__init__.py

# brew postinstall python
# TODO:  WARNING: The script pycodestyle is installed in '/Users/alessandro/Library/Python/3.7/bin' which is not on PATH.


