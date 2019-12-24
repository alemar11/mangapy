import asyncio
import aiohttp
import re
import requests
from execjs import compile

from mangapy.mangarepository import MangaRepository, Manga, Chapter
from collections import namedtuple
import urllib.request
from bs4 import BeautifulSoup



session = requests.Session()

#https://gist.github.com/tanat/592a559b66561f90907e1418eca82cf3
#https://docs.aiohttp.org/en/latest/client_advanced.html

def exec_js(source, js):  # pragma: no cover
    return compile(source).eval(js)


def baseN(num, b, numerals="0123456789abcdefghijklmnopqrstuvwxyz"):
    return ((num == 0) and numerals[0]) or (baseN(num // b, b, numerals).lstrip(numerals[0]) + numerals[num % b])


def unpack(p, a, c, k, e=None, d=None):
    while (c):
        c -= 1
        if (k[c]):
            p = re.sub("\\b" + baseN(c, a) + "\\b",  k[c], p)
    return p


class MangaFoxRepository(MangaRepository):
    name = "MangaFox"
    base_url = "http://fanfox.net"
    cookies = {'isAdult': 1}

    '''
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
    '''    

    def search(self, title):
        pass   


    async def _search(self, manga_name):
        # support alphanumeric names with multiple words
        manga_name_adjusted = re.sub(r'[^A-Za-z0-9]+', '_', re.sub(r'^[^A-Za-z0-9]+|[^A-Za-z0-9]+$', '', manga_name)).lower()
        manga_url = "{0}/manga/{1}".format(self.base_url, manga_name_adjusted)
        
        # connector = aiohttp.TCPConnector(
        #     verify_ssl=False,
        #     ttl_dns_cache=60,
        #     limit=1000,
        #     limit_per_host=20
        # )

        headers = {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=1.0,image/webp,image/apng,*/*;q=1.0', 
            'Accept-Encoding': 'gzip, deflate',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_13_2) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/63.0.3239.108 Safari/537.36',
            'Referer': 'http://fanfox.net'
            }

        response = session.get(url=manga_url, headers=headers)

       
        # if response is None or response.status != 200:
        #     return None

        content = response.text

        soup = BeautifulSoup(content)
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


ChapterMetadata = namedtuple("ChapterMetadata", "comic_id chapter_id image_count, key")

class MangaFoxChapter(Chapter):

    headers = {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=1.0,image/webp,image/apng,*/*;q=1.0', 
            'Accept-Encoding': 'gzip, deflate',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_13_2) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/63.0.3239.108 Safari/537.36',
            'Referer': 'http://fanfox.net'
            }

    def _get_links(self, content):
        js = re.search(r'eval\((function\b.+)\((\'[\w ].+)\)\)', content).groups()
        return exec_js('m = ' + js[0], 'm(' + js[1] + ')')

    def _one_link_helper(self, content, page, base_url):
        cid = re.search(r'chapterid\s*=\s*(\d+)', content).group(1)
        #base_url = '/' #self.chapter[0:self.chapter.rfind('/')]
        links = self._get_links(content)
        key = ''.join(re.findall(r'\'(\w)\'', links))
        final_url = '{}/chapterfun.ashx?cid={}&page={}&key={}'.format(
            base_url,
            cid,
            page,
            key
        )
        print(final_url)

        # request = urllib.request.Request(final_url)
        # request.add_header('User-Agent', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_13_2) AppleWebKit/537.36 \
        #                       (KHTML, like Gecko) Chrome/63.0.3239.108 Safari/537.36')

        # request.add_header('Cookie', 'isAdult=1')
        # request.add_header('Cookie', _cookies)     
        # response = urllib.request.urlopen(request, timeout=5)

        response = session.get(final_url, headers=self.headers)

        content = response.text
        return content
        # return self.http_get('{}/chapterfun.ashx?cid={}&page={}&key={}'.format(
        #     base_url,
        #     cid,
        #     page,
        #     key
        # ))

    def metadata(self, page):
        test_url = 'http://fanfox.net/manga/naruto/v01/c000/13.html'

        # request = urllib.request.Request(test_url)
        # request.add_header('User-Agent', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_13_2) AppleWebKit/537.36 \
        #                       (KHTML, like Gecko) Chrome/63.0.3239.108 Safari/537.36')

        # request.add_header('Cookie', 'isAdult=1')
        # response = urllib.request.urlopen(request, timeout=5)
        # cookies = response.getheader('Set-Cookie')

        response = session.get(test_url, headers=self.headers)

        content = response.text
        soup = BeautifulSoup(content)
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

        return ChapterMetadata(comic_id, chapter_id, int(image_count), key)
                    


    def pages(self):

        base_url = self.first_page_url[:self.first_page_url.rfind('/')]    
        # print(base_url) 
        # request = urllib.request.Request(self.first_page_url)
        # request.add_header('User-Agent', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_13_2) AppleWebKit/537.36 \
        #                       (KHTML, like Gecko) Chrome/63.0.3239.108 Safari/537.36')

        # request.add_header('Cookie', 'isAdult=1')
        # #request.add_header('Cookie', metadata.cookies)     
        # response = urllib.request.urlopen(request, timeout=5)
        # content = response.read()
        # _cookies = response.getheader('Set-Cookie')

        #content = requests.get(self.first_page_url).content

        # headers = {
        #     'User-Agent': 'My User Agent 1.0'}


        response = session.get(self.first_page_url, headers=self.headers)
        content = response.text

        soup = BeautifulSoup(content, features="html.parser")
        page_numbers = soup.findAll("a", {"data-page": True})

        page_numbers = map(lambda x: int(x['data-page']), page_numbers)
        first_page_number = 1
        last_page_number = max(page_numbers)
        last_page = soup.select('.pager-list-left > span > a:nth-last-child(2)')

        #last_page = self.document_fromstring(content, '.pager-list-left > span > a:nth-last-child(2)', 0)
        links = []
        for i in range(0, int(last_page_number / 2 + .5)):
            data = self._one_link_helper(soup.text, (i * 2) + 1, base_url)
            links += self._parse_links(self._get_links(data))

        print(links)


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
        '''    



if __name__ == '__main__':
    repository = MangaFoxRepository()
    manga = asyncio.run(repository._search("naruto"))
    firstChapter = manga.chapters[0]
    firstChapter.pages()


#repository.search("kimetsu no yaiba")
# test: Kimetsu no Yaiba: Tomioka Giyuu Gaiden

#repository.search('Kimetsu no Yaiba: Tomioka Giyuu Gaiden')


#repository.suggest("kimetsu")
#repository.search('Free! dj - Kekkon Shitara Dou Naru!?') # adult content
#http://fanfox.net/manga/gentleman_devil/v01/c038/1.html # adult content
