from aiohttp import ClientSession
import asyncio
from tqdm import tqdm
import glob
import os
from PIL import Image
from urllib.parse import urlparse
from mangapy.mangarepository import Chapter


class AsyncDownloader(object):
    def __init__(self, concurrent_connections=100, silent=False):
        self.concurrent_connections = concurrent_connections
        self.silent = silent
        self.progress_bar = None
        self.loop = asyncio.get_event_loop()
        self.semaphore = asyncio.Semaphore(concurrent_connections)

    async def fetch(self, session, url):
        async with self.semaphore:
            async with session.get(url) as response:
                task = asyncio.create_task(response.read())
                resp = await task

                await response.release()
                if not self.silent:
                    self.progress_bar.update(1)
                return resp

    async def batch_download(self, urls, auth=None):
        async with ClientSession() as session:
            await asyncio.gather(*[asyncio.create_task(self.download_and_save(session, url)) for url in urls])

    async def download_and_save(self, session, url):
        task = asyncio.ensure_future(self.fetch(session, url))
        content = await task

    def download(self, urls):
        self.progress_bar = tqdm(urls, total=len(urls), desc='Reveived', unit='requests')
        self.progress_bar.update(0)

        tasks = self.batch_download(urls)
        self.loop.run_until_complete(tasks)


### call like so ###

URL_PATTERN = 'https://www.example.com/{}.html'

def gen_url(lower=0, upper=None):
    for i in range(lower, upper):
        yield URL_PATTERN.format(i)   

if __name__ == "__main__":
    from mangapy.mangapark import MangaParkRepository

    #repository = MangaParkRepository()
    #manga = repository.search("naruto")

    from tqdm import trange
    from time import sleep

    ad = AsyncDownloader(concurrent_connections=30)
    data = ad.download([g for g in gen_url(upper=1000)])
