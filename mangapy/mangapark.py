import requests
import json
import re
import urllib3
from mangapy import log
from mangapy.mangarepository import MangaRepository, Manga, Chapter, Page
from bs4 import BeautifulSoup

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class MangaParkRepository(MangaRepository):
    name = "MangaPark"
    base_url = "https://mangapark.net"
    proxies = None
    _session = None

    @property
    def session(self):
        if self._session is not None:
            return self._session

        self._session = requests.Session()
        headers = {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=1.0,image/webp,image/apng,*/*;q=1.0',
            'Accept-Encoding': 'gzip, deflate',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
                          'Chrome/60.0.3112.101 Safari/537.36',
            'Accept-Language': 'ru-RU,ru;q=0.8,en-US;q=0.5,en;q=0.3',
            'Referer': 'https://mangapark.net/',
            'Connection': 'keep-alive'
        }
        self._session.cookies['set'] = 'theme=1&h=1&img_load=5&img_zoom=1&img_tool=1&twin_m=0' \
                                       '&twin_c=0&manga_a_warn=1&history=1&timezone=14'
        self._session.headers = headers
        self._session.proxies = self.proxies
        return self._session

    def search(self, title) -> [Manga]:
        manga_name_adjusted = re.sub(r'[^A-Za-z0-9]+', '-', re.sub(r'^[^A-Za-z0-9]+|[^A-Za-z0-9]+$', '', title)).lower()
        manga_url = "{0}/manga/{1}".format(self.base_url, manga_name_adjusted)
        response = self.session.get(url=manga_url, verify=False)
        if response is None or response.status_code != 200:
            return None

        text = response.text
        soup = BeautifulSoup(text, "html.parser")

        # this algorithm searches for the most updated stream and for the most content rich stream
        # if the 2 found streams are different, the two streams chapters will be merged
        # 1 fox
        # 3 panda
        # 6 rock
        # 4 duck
        # 101 mini
        streams = ['stream_1', 'stream_3', 'stream_6', 'stream_4', 'stream_101']
        contents = {}
        for stream in streams:
            content = soup.find('div', {'id': stream})
            if content is not None:
                list = self.parse_chapters(content)
                if list is not None:
                    log.info('content found for stream {0}'.format(stream))
                    contents[stream] = list
                else:
                    log.warning('content not found for stream {0}'.format(stream))

        if len(contents) == 0:
            log.warning('No chapters found')
            return None

        last_chapter_number = -1
        most_recenly_updated_stream = None
        number_of_chapters = -1
        most_rich_content_stream = None

        for stream, chapters in contents.items():
            max_chapter_number = max(chapter.number for chapter in chapters)
            if max_chapter_number is not None and max_chapter_number > last_chapter_number:
                last_chapter_number = max_chapter_number
                manga_chapters = chapters
                most_recenly_updated_stream = stream
            if most_rich_content_stream is not None:
                if len(chapters) > number_of_chapters:
                    number_of_chapters = len(chapters)
                    most_rich_content_stream = stream
            else:
                number_of_chapters = len(chapters)
                most_rich_content_stream = stream

        if most_recenly_updated_stream == most_rich_content_stream:
            log.info('using {0}'.format(most_recenly_updated_stream))
            manga_chapters = contents[most_recenly_updated_stream]
        else:
            # at this point we have 2 sources: one with the latest chapter and another one with probably the entire chapter list
            log.info('using {0} and {1}'.format(most_recenly_updated_stream, most_rich_content_stream))
            available_chapters = contents[most_recenly_updated_stream] + contents[most_rich_content_stream]
            seen = set()
            manga_chapters = []
            for chapter in available_chapters:
                if chapter.number not in seen:
                    manga_chapters.append(chapter)
                    seen.add(chapter.number)
               
            manga_chapters = sorted(manga_chapters, key=lambda chapter: chapter.number, reverse=False)

        manga = Manga(title, manga_chapters)
        return manga

    def parse_chapters(self, content):
        # parses all the chapter for a stream content
        # any minor version discovered (i.e. 11.4) will update the major version (i.e. 11)
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
            # https://regex101.com/r/PFFb5l/10
            match = re.search(
                r'((?<=ch.)([0-9]*)|(?<=Chapter)\s*-?([0-9]*[.]?[0-9])|(?<=Page)\s*-?([0-9]*[.]?[0-9]))',
                metadata.title)
            if match is not None:
                try:
                    number = match.group(1) or 0
                    number = float(number)
                except ValueError:
                    number = 0
            else:
                number = 0

            if number == 0 and number in manga_chapters.keys():
                # some streams uses ch 0 in different volumes to identify side stories
                # i.e. Vol.23 Chapter 0: Side-A the sand
                # those chapter will be skipped
                log.warning('skipping chapter {0}'.format(metadata.title))
                continue

            url = metadata.url
            chapter_url = "{0}{1}".format(self.base_url, url)
            chapter = MangaParkChapter(chapter_url, abs(number))
            manga_chapters[number] = chapter

        sorted_chapters = sorted(manga_chapters.values(), key=lambda chapter: chapter.number, reverse=False)
        return sorted_chapters


class MangaParkChapter(Chapter):
    def pages(self) -> [Page]:
        response = requests.get(url=self.first_page_url, verify=False)
        pages = []

        if response is None or response.status_code != 200:
            return pages

        content = response.text
        soup = BeautifulSoup(content, "html.parser")
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


if __name__ == '__main__':
    repo = MangaParkRepository()
    manga = repo.search('naruto')
    assert manga is not None
