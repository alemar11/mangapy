import aiohttp
import json
import re

from mangapy.mangarepository import MangaRepository, Manga, Chapter, Page, download
from bs4 import BeautifulSoup


class MangaParkRepository(MangaRepository):
    name = "MangaPark"
    base_url = "https://mangapark.net"
    cookies = {'set': 'theme=1&h=1&img_load=5&img_zoom=1&img_tool=1&twin_m=0&twin_c=0&manga_a_warn=1&history=1&timezone=14'}

    # TODO: @property and static methods

    def suggest(self, manga_name):
        return None

    async def search(self, manga_name):
        manga_name_adjusted = re.sub(r'[^A-Za-z0-9]+', '-', re.sub(r'^[^A-Za-z0-9]+|[^A-Za-z0-9]+$', '', manga_name)).lower()
        manga_url = "{0}/manga/{1}".format(self.base_url, manga_name_adjusted)
        async with aiohttp.ClientSession() as session:
            async with session.get(url=manga_url, cookies=self.cookies) as response:
                if response is None or response.status != 200:

                    return None

                body = await response.content.read()
                soup = BeautifulSoup(body, "html.parser")
            
                # 1 fox
                # 3 panda
                # 6 rock
                # 4 duck
                # 101 mini

                '''
                TODO: possible optimization
                fetch the last chapter for every streams and determine the stream that has
                the bigger chapter (decimal excluded) and most recently updated
                '''

                streams = ['stream_1', 'stream_3', 'stream_6', 'stream_4', 'stream_101']
                content = None
                for stream in streams:
                    content = soup.find('div', {'id': stream})
                    if content is not None:
                        break

                if content is None:
                    '''
                    warning = soup.find('div', {'class': 'warning'})
                    if warning is not None:
                        print("Adult content")
                    '''    
                    return None

                chapters_detail = content.select('a.ml-1')

                if chapters_detail is None:
                    return None

                chapters_url = map(lambda c: c['href'], reversed(chapters_detail))
                manga_chapters = []
                
                for url in chapters_url:
                    splits = chapter_relative_url = url.rsplit('/', 1)
                    last_path = splits[-1]
                    chapter_relative_url = url
                    try:
                        prefix = last_path[0]
                        if prefix.lower() == 'c':
                            chapter_number = float(last_path[1:])  # if it's a float, we can get the chapter number
                            chapter_relative_url = splits[0]
                        else: # one volume
                            chapter_number = float(0)    
                            chapter_relative_url = url
                    except ValueError:
                        chapter_number = 0
                        pass  # it was a string, not a float.

                    chapter_url = "{0}{1}".format(self.base_url, chapter_relative_url)
                    chapter = MangaParkChapter(chapter_url, chapter_number)
                    manga_chapters.append(chapter)
                
                manga = Manga(
                    manga_name,
                    manga_chapters
                )
                return manga


class MangaParkChapter(Chapter):
    async def pages(self):
        async with aiohttp.ClientSession() as session:
            async with session.get(url=self.first_page_url) as response:
                pages = []

                if response is None or response.status != 200:
                    return pages
  
                body = await response.content.read()
                soup = BeautifulSoup(body, "html.parser")
                scripts = soup.findAll('script')
                generator = (script for script in scripts if script.text.find('var _load_pages') > 0)
                for script in generator:
                    match = re.search(r'(var _load_pages\s*=\s*)(.+)(?=;)', script.text)
                    json_payload = match.group(2)
                    json_pages = json.loads(json_payload)
                    for page in json_pages:
                        url = page['u']
                        if url.startswith('//'):
                            url = 'https:' + page['u']
                        pages.append(Page(page['n'], url))
                return pages



'''
if __name__ == "__main__":
    import asyncio
    loop = asyncio.get_event_loop()
    repository = MangaParkRepository()

    manga = asyncio.run(repository.search("naruto"))

    #manga = repository.search("naruto")

    if manga is not None:
        print(len(manga.chapters))
        firstChapter = manga.chapters[0]
        secondChapter = manga.chapters[1]
        thirdChapter = manga.chapters[2]
        lastChapter = manga.chapters[-1]
        #asyncio.run(firstChapter.download(path='~/Downloads/mangapy'))
        #asyncio.run(download(firstChapter, '~/Downloads/mangapy'))

        path = '~/Downloads/mangapy'

        tasks = [
            download(lastChapter, path),
            #download(firstChapter, path),
            #download(secondChapter, path),
            #download(thirdChapter, path)
            ]

        #https://www.educative.io/blog/python-concurrency-making-sense-of-asyncio    
        loop.run_until_complete(asyncio.wait(tasks))
        loop.close()
'''