from aiohttp import ClientSession
import asyncio
from tqdm import tqdm
import glob
import os
from PIL import Image
from urllib.parse import urlparse
from mangapy.mangarepository import Chapter
from threading import Thread, current_thread


class MangaException(Exception):
    """Exception class for manga"""
    pass


class ChapterDownloader(object):
    def __init__(self, concurrent_connections=5, silent=False):
        self.concurrent_connections = concurrent_connections
        self.silent = silent
        self.progress_bar = None
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.semaphore = asyncio.Semaphore(concurrent_connections, loop=self.loop)  

    def __del__(self):
        self.loop.close()

    async def fetch(self, session: ClientSession, url: str):
        async with self.semaphore:
            try:
                async with session.get(url) as response:
                    if response.status != 200 and response.content is not None:
                        return None
                    else:
                        content = await response.content.read()
                        await response.release()
                        if not self.silent:
                            self.progress_bar.update(1)
                        return content
            except OSError as msg:
                print(msg)

    async def save(self, session: ClientSession, url: str, path: str, file_name: str):
        file_ext = urlparse(url).path.split('.')[-1]
        data = await self.fetch(session, url)
        if data is None:
            return
        dir = os.path.expanduser(path)
        if not os.path.isdir(path):
            try:
                os.makedirs(dir, exist_ok=True)
            except OSError as msg:
                raise MangaException(msg)

        file = os.path.join(dir, file_name + '.' + file_ext)
        output = open(file, "wb")
        output.write(data)
        output.close()

    def start(self, chapter: Chapter, to: str):
        self.loop.run_until_complete(self.download(chapter, to))

    async def download(self, chapter: Chapter, to: str):
        async with ClientSession() as session:
            to = os.path.join(to, str(chapter.number))
            tasks = []
            _pages = await chapter.pages()
            self.progress_bar = tqdm(_pages, total=len(_pages), desc='Chapter {0}', unit='pages')
            self.progress_bar.update(0)

            for page in _pages:
                url = page.url
                tasks.append(self.save(session, url, to, str(page.number)))

            await asyncio.gather(*tasks)




def do_stuff(c: Chapter):
    cd = ChapterDownloader()
    cd.start(c,'~/Downloads/__man')
    #ad = AsyncDownloader(concurrent_connections=30)
    #data = ad.download([g for g in gen_url(upper=1000)])



def main():
    from mangapy.mangapark import MangaParkRepository
    repository = MangaParkRepository()
    manga = repository.search("naruto")
    if manga is not None:
        firstChapter = manga.chapters[0]
        secondChapter = manga.chapters[1]
        thirdChapter = manga.chapters[2]
        lastChapter = manga.latest
       
        chapters = [firstChapter, secondChapter, thirdChapter, lastChapter]

        threads = [Thread(target=do_stuff, args=(c,)) for c in chapters]
        [thread.start() for thread in threads]
        [thread.join() for thread in threads]


if __name__ == "__main__":
    main()