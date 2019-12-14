import re
import time

from utils import get_page_soup
from MangaRepository import MangaRepository, Manga, Chapter, Page
from collections import namedtuple
import urllib.request
from bs4 import BeautifulSoup


def baseN(num, b, numerals="0123456789abcdefghijklmnopqrstuvwxyz"):
    return ((num == 0) and numerals[0]) or (baseN(num // b, b, numerals).lstrip(numerals[0]) + numerals[num % b])


def unpack(p, a, c, k, e=None, d=None):
    while (c):
        c -= 1
        if (k[c]):
            p = re.sub("\\b" + baseN(c, a) + "\\b",  k[c], p)
    return p

class MangaFox(MangaRepository):
    name = "MangaFox"
    base_url = "https://fanfox.net"

    def suggest(self, manga_name):
        manga_name_adjusted = re.sub(r'[^A-Za-z0-9]+', '+', re.sub(r'^[^A-Za-z0-9]+|[^A-Za-z0-9]+$', '', manga_name))
        manga_name_adjusted = manga_name_adjusted.lower()
        search_sort_options = ''
        search_url = '{0}/search?name={1}&{2}'.format(
            self.base_url,
            manga_name_adjusted,
            search_sort_options)
        soup = get_page_soup(search_url)
        suggestions_detail = soup.find('ul', {'class': 'manga-list-4-list line'})

        if suggestions_detail is None:
            return None
      
        li = suggestions_detail.findChildren('li')
        titles = map(lambda l: l.find('a')['title'], li)
        titles = list(filter(None.__ne__, titles))

        return titles

    def search(self, manga_name):
        # support alphanumeric names with multiple words
        manga_name_adjusted = re.sub(r'[^A-Za-z0-9]+', '_', re.sub(r'^[^A-Za-z0-9]+|[^A-Za-z0-9]+$', '', manga_name)).lower()
        manga_url = "{0}/manga/{1}/".format(self.base_url, manga_name_adjusted)
        soup = get_page_soup(manga_url)
        chapters_detail = soup.find('ul', {'class': 'detail-main-list'})
        
        if chapters_detail is None:
            return None
        
        chapters = chapters_detail.findAll('a', href=True)
        chapters_url = map(lambda c: c['href'], reversed(chapters))
        manga_chapters = []
        
        for url in chapters_url:
            number = url.split("/")[-2][1:]  # relative url, todo: regex
            absolute_url = "{0}{1}".format(self.base_url, url)
            chapter = MangaFoxChapter(absolute_url, number)
            manga_chapters.append(chapter)
        
        manga = Manga(
            manga_name,
            manga_chapters
        )
        # TODO: @property and static methods
        return manga


ChapterMetadata = namedtuple("ChapterMetadata", "comic_id chapter_id image_count, key, cookies")

class MangaFoxChapter(Chapter):
    def hello(self):
        print("hello")

    def metadata(self, page):
        test_url = 'http://fanfox.net/manga/naruto/v01/c000/13.html'

        request = urllib.request.Request(test_url)
        request.add_header('User-Agent', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_13_2) AppleWebKit/537.36 \
                              (KHTML, like Gecko) Chrome/63.0.3239.108 Safari/537.36')

        request.add_header('Cookie', 'isAdult=1')
        response = urllib.request.urlopen(request, timeout=5)
        cookies = response.getheader('Set-Cookie')


        page_content = response.read()
        soup = BeautifulSoup(page_content, "html.parser")
        #soup = get_page_soup(test_url)

        comic_id = None
        chapter_id = None
        image_count = None
        key = None

        for script in soup.find_all("script", {"src": False}):
            comic_id_match = re.search(r'(var comicid\s*=\s*)([0-9]+)(?=;)', script.string)
            if comic_id_match:
                comic_id = comic_id_match.group(2)
            
            chapter_id_match = re.search(r'(var chapterid\s*=\s*)([0-9]+)(?=;)', script.string)
            if chapter_id_match:
                chapter_id = chapter_id_match.group(2)
                
            image_count_match = re.search(r'(var imagecount\s*=\s*)([0-9]+)(?=;)', script.string)
            if image_count_match:
                image_count = image_count_match.group(2)

            if script.string.startswith(' eval(function(p,a,c,k,e,d)'):
                text = script.string.rstrip("\n\r")

                if text == '':
                    continue

                encrypted = text.split('}(')[1][:-1]
                unpacked = eval('unpack(' + encrypted) # https://www.strictly-software.com/unpack-javascript
                key_match = re.search(r'(?<=var guidkey=)(.*)(?=\';)', unpacked)
                _key = key_match.group(1)
                _key = _key.replace('\'', '')
                _key = _key.replace('\\', '')
                _key = _key.replace('+', '')
                key = _key


        if comic_id is None or chapter_id is None or image_count is None or key is None:
            return None

        return ChapterMetadata(comic_id, chapter_id, int(image_count), key, cookies)
                    


    def pages(self):
        '''
        soup = get_page_soup(self.first_page_url)
        page_numbers = soup.findAll("a", {"data-page": True})

        page_numbers = map(lambda x: int(x['data-page']), page_numbers)
        first_page_number = 1
        last_page_number = max(page_numbers)
        '''

        metadata = self.metadata(self.first_page_url)

        # http://fanfox.net/manga/gentleman_devil/v03/c038/chapterfun.ashx

        # http://fanfox.net/manga/naruto/v72/c000/1.html
        # http://fanfox.net/manga/naruto/v72/c700.6/chapterfun.ashx?cid=370505&page=1&key=

        url = self.first_page_url[:self.first_page_url.rfind('/')]
        url += '/chapterfun.ashx?cid={0}&page={1}&key={2}'.format(metadata.chapter_id, 1, metadata.key)        

        #url = 'http://fanfox.net/manga/naruto/v72/c700.6/chapterfun.ashx?cid=370505&page=1&key={0}'.format(metadata.key)
        #url = 'http://fanfox.net/manga/naruto/v72/c700.6/history.ashx?cid=370505&mid=8&page=1&uid=0'
        request = urllib.request.Request(url)
        request.add_header('User-Agent', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_13_2) AppleWebKit/537.36 \
                              (KHTML, like Gecko) Chrome/63.0.3239.108 Safari/537.36')
        request.add_header('Cookie', metadata.cookies)                              

        encrypted = None
        max_attempts = 100
        i = 1
        while encrypted is None:
            print(i)
            if i != 1:
                time.sleep(2.4)
            i += 1
            response = urllib.request.urlopen(request, timeout=5)
            content = response.read()
            if content is None:
                continue

            body = content
            body = body.decode().rstrip("\n\r")

            if body == '':
                continue

            encrypted = body.split('}(')[1][:-1]
            unpacked = eval('unpack(' + encrypted) # https://www.strictly-software.com/unpack-javascript

        print('found')

        pages = []
        for i in range(first_page_number, last_page_number): # TODO this not consider the last page
            page_url = re.sub(r'(?<=\/)[0-9]+(?=.html)', str(i), self.first_page_url)
            #print(page_url)
            page = Page("name", page_url)
            pages.append(page)


repository = MangaFox()
manga = repository.search("naruto")
firstChapter = manga.chapters[0]
firstChapter.pages()


#repository.search("kimetsu no yaiba")
# test: Kimetsu no Yaiba: Tomioka Giyuu Gaiden

#repository.search('Kimetsu no Yaiba: Tomioka Giyuu Gaiden')


#repository.suggest("kimetsu")
#repository.search('Free! dj - Kekkon Shitara Dou Naru!?') # adult content
#http://fanfox.net/manga/gentleman_devil/v01/c038/1.html # adult content
