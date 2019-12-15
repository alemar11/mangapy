import re
import requests
import json

from MangaRepository import MangaRepository, Manga, Chapter, Page
from bs4 import BeautifulSoup


class MangaPark(MangaRepository):
    name = "MangaFox"
    base_url = "https://mangapark.net"
    cookies = {'set': 'theme=1&h=1&img_load=5&img_zoom=1&img_tool=1&twin_m=0&twin_c=0&manga_a_warn=1&history=1&timezone=14'}

    def suggest(self, manga_name):
        return None
        
    def search(self, manga_name):    
        # support alphanumeric names with multiple words
        manga_name_adjusted = re.sub(r'[^A-Za-z0-9]+', '-', re.sub(r'^[^A-Za-z0-9]+|[^A-Za-z0-9]+$', '', manga_name)).lower()
        manga_url = "{0}/manga/{1}".format(self.base_url, manga_name_adjusted)
        response = requests.get(manga_url, verify=False, cookies=self.cookies)

        if response is None or response.status_code != 200:
            return None

        body = response.text
        soup = BeautifulSoup(body, "html.parser")
       
        # 1 fox
        # 3 panda
        # 6 rock
        # 4 duck
        # 101 mini
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
            # TODO (bug): /manga/naruto-eroi-no-vol-1-doujinshi/i1737519 (in this case we don't have a number nor a /1)
            chapter_number = url.split("/")[-2][1:]
            chapter_relative_url = url.rsplit('/', 1)[0]
            chapter_url = "{0}{1}".format(self.base_url, chapter_relative_url)
            chapter = MangaParkChapter(chapter_url, chapter_number)
            manga_chapters.append(chapter)
        
        manga = Manga(
            manga_name,
            manga_chapters
        )
        # TODO: @property and static methods
        return manga


class MangaParkChapter(Chapter):
    def pages(self):
        response = requests.get(self.first_page_url, verify=False)
        if response is None or response.status_code != 200:
            return None

        body = response.text
        soup = BeautifulSoup(body, "html.parser")
        scripts = soup.findAll('script')
        generator = (script for script in scripts if script.text.find('var _load_pages') > 0)

        for script in generator:
            match = re.search(r'(var _load_pages\s*=\s*)(.+)(?=;)', script.text)
            json_payload = match.group(2)
            json_pages = json.loads(json_payload)
            for page in json_pages:
                yield Page(page['n'], page['u'])


repository = MangaPark()
#manga = repository.search("naruto")
#manga = repository.search('emergence') # adult content
manga = repository.search('Naruto - Eroi no Vol.1 (Doujinshi)')  # adult content
if manga is not None:
    print(len(manga.chapters))
    firstChapter = manga.chapters[0]
    pages = firstChapter.pages()
    for page in pages:
        print(page.number)
