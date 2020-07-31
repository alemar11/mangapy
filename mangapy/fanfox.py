import re
import requests
from mangapy import log
from mangapy.mangarepository import MangaRepository, Manga, Chapter, Page
from bs4 import BeautifulSoup


def unpack(p, a, c, k, e=None, d=None):
    def baseN(num, b, numerals="0123456789abcdefghijklmnopqrstuvwxyz"):
        return ((num == 0) and numerals[0]) or (baseN(num // b, b, numerals).lstrip(numerals[0]) + numerals[num % b])

    while (c):
        c -= 1
        if (k[c]):
            p = re.sub("\\b" + baseN(c, a) + "\\b",  k[c], p)
    return p


class FanFoxRepository(MangaRepository):
    name = "FanFox"
    base_url = "http://fanfox.net"
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
            'Referer': 'http://fanfox.net',
            'Connection': 'keep-alive'
        }

        self._session.cookies['isAdult'] = '1'
        self._session.headers = headers
        self._session.proxies = self.proxies
        return self._session

    def _get_chapters(self, list):
        manga_chapters = []
        if list is None:
            return manga_chapters            
        list_detail = list.find('ul', {'class': 'detail-main-list'})
        if list_detail is None:
            return manga_chapters
        chapters = list_detail.findAll('a', href=True)
        chapters_url = map(lambda c: c['href'], reversed(chapters))
         
        for url in chapters_url:
            number = url.split("/")[-2][1:]  # relative url, todo: regex
            absolute_url = "{0}{1}".format(self.base_url, url)
            number = float(number)
            chapter = FanFoxChapter(absolute_url, number, self.session)
            manga_chapters.append(chapter)

        return manga_chapters

    def search(self, manga_name) -> [Manga]:
        # support alphanumeric names with multiple words
        manga_name_adjusted = re.sub(r'[^A-Za-z0-9]+', '_', re.sub(r'^[^A-Za-z0-9]+|[^A-Za-z0-9]+$', '', manga_name)).lower()
        manga_url = "{0}/manga/{1}".format(self.base_url, manga_name_adjusted)
        response = self.session.get(url=manga_url)

        if response is None or response.status_code != 200:
            return None

        content = response.text
        soup = BeautifulSoup(content, features="html.parser")

        # list-2 contains all the chapters, list-1 only the last volume
        # in theory we should use list-1 and fallback to to list-2 if list-1 doesn't exist
        # but it seems that sometimes chapters are put in the wrong list
        # to solve this we merge both the lists
        list_two = soup.find('div', {'id': 'list-2'})
        list_one = soup.find('div', {'id': 'list-1'})

        if list_one is None and list_two is None:
            blocked = soup.find('p', {'class': 'detail-block-content'})
            if blocked:
                log.warning(blocked.getText())
            else:
                log.warning('No chapters found')
            return None

        list_one_chapters = self._get_chapters(list_one)
        list_two_chapters = self._get_chapters(list_two)
        chapters = list_one_chapters + list_two_chapters

        if not chapters:
            log.warning('No chapters list found')
            return None

        seen = set()
        unique_chapters = []
        for chapter in chapters:
            if chapter.number not in seen:
                unique_chapters.append(chapter)
                seen.add(chapter.number)
               
        sorted_chapters = sorted(unique_chapters, key=lambda chapter: chapter.number, reverse=False)

        manga = Manga(manga_name, sorted_chapters)
        return manga


class FanFoxChapter(Chapter):
    def __init__(self, first_page_url, number, session: requests.Session):
        self.first_page_url = first_page_url
        self.number = number
        self.session = session

    def _get_urls(self, content):
        js = re.search(r'eval\((function\b.+)\((\'[\w ].+)\)\)', content).group(0)
        encrypted = js.split('}(')[1][:-1]
        unpacked = eval('unpack(' + encrypted)
        return unpacked

    def _get_key(self, content):
        js = re.search(r'eval\((function\b.+)\((\'[\w ].+)\)\)', content).group(0)
        encrypted = js.split('}(')[1][:-1]
        unpacked = eval('unpack(' + encrypted)
        key_match = re.search(r'(?<=var guidkey=)(.*)(?=\';)', unpacked)
        key = key_match.group(1)
        key = key.replace('\'', '')
        key = key.replace('\\', '')
        key = key.replace('+', '')
        return key

    def _one_link_helper(self, content, page, base_url):
        cid = re.search(r'chapterid\s*=\s*(\d+)', content).group(1)
        key = self._get_key(content)
        final_url = '{}/chapterfun.ashx?cid={}&page={}&key={}'.format(base_url, cid, page, key)
        response = self.session.get(final_url)

        if response is None or response.status_code != 200:
            return None

        content = response.text
        return content

    def _parse_links(self, data):
        base_path = re.search(r'pix="(.+?)"', data).group(1)
        images = re.findall(r'"(/\w.+?)"', data)
        return [base_path + i for i in images]

    def pages(self) -> [Page]:
        base_url = self.first_page_url[:self.first_page_url.rfind('/')]
        response = self.session.get(self.first_page_url)

        if response is None or response.status_code != 200:
            return None

        content = response.text
        soup = BeautifulSoup(content, features="html.parser")
        page_numbers = soup.findAll("a", {"data-page": True})
        page_numbers = map(lambda x: int(x['data-page']), page_numbers)
        last_page_number = max(page_numbers)

        links = []
        for i in range(0, int(last_page_number / 2 + .5)):
            data = self._one_link_helper(content, (i * 2) + 1, base_url)
            links += self._parse_links(self._get_urls(data))

        pages = []
        for i, link in enumerate(links):
            pages.append(Page(i, link))

        return pages


if __name__ == '__main__':
    repo = FanFoxRepository()
    manga = repo.search('naruto')
    assert manga is not None
