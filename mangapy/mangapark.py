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
                streams = ['stream_1', 'stream_3', 'stream_6', 'stream_4', 'stream_101']
                contents = {}
                for stream in streams:
                    print(stream)
                    content = soup.find('div', {'id': stream})
                    if content is not None:
                        list = self.parse_chapters(content)
                        if list is not None:
                            print("     content found")
                            contents[stream] = list
                        else:
                            print("     content NOT found")    

                last_chapter_number = -1
                most_updated_stream = None

                for stream, chapters in contents.items():
                    max_chapter_number = max(chapter.number for chapter in chapters)
                    if max_chapter_number is not None and max_chapter_number > last_chapter_number:
                        last_chapter_number = max_chapter_number
                        manga_chapters = chapters
                        most_updated_stream = stream

                manga_chapters = contents[most_updated_stream]
                print("Using: " + most_updated_stream + ' with last chapter: ' + str(last_chapter_number))
                
                manga = Manga(manga_name, manga_chapters)
                return manga

    def parse_chapters(self, content):
        chapters_detail = content.select('a.ml-1')
        if chapters_detail is None:
            return None

        class Metadata:
            def __init__(self, url, title):
                self.url = url
                self.title = title

        manga_chapters = {}
        chapters_metadata = map(lambda c: Metadata(c['href'], c.string), reversed(chapters_detail))

        for metadata in chapters_metadata:
            # https://regex101.com/r/PFFb5l/9/
            # any minor version discovered (i.e. 11.4) will update the major version (i.e. 11)
            match = re.search(r'((?<=ch.)([0-9]*)|(?<=Chapter)\s*-?([0-9]*))', metadata.title)
            if match is not None:
                try:
                    number = match.group(1) or 0
                    number = int(number)
                except ValueError:
                    number = 0
            else:
                number = 0         

            if number == 0:
                print('❌ ' + metadata.title)
                # TODO: skip side stories inside volumes unless the volume is the 0 or 1
                # but if there is vol.0  without chapter it's ok to keepet (test with naruto)

            url = metadata.url
            chapter_url = "{0}{1}".format(self.base_url, url)
            chapter = MangaParkChapter(chapter_url, abs(number))
            manga_chapters[number] = chapter

        sorted_chapters = sorted(manga_chapters.values(), key=lambda x: x.number, reverse=False)    
        return sorted_chapters


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


if __name__ == "__main__":
    import asyncio
    loop = asyncio.get_event_loop()
    repository = MangaParkRepository()
    manga = asyncio.run(repository.search("naruto"))

    if manga is not None:
        firstChapter = manga.chapters[0]
        secondChapter = manga.chapters[1]
        thirdChapter = manga.chapters[2]
        lastChapter = manga.latest
        #asyncio.run(firstChapter.download(path='~/Downloads/mangapy'))
        #asyncio.run(download(firstChapter, '~/Downloads/mangapy'))

        path = '~/Downloads/mangapy'

        tasks = [
            download(lastChapter, path),
            #download(firstChapter, path),
            #download(secondChapter, path),
            #download(thirdChapter, path)
            ]

        loop.run_until_complete(asyncio.wait(tasks))
        loop.close()
