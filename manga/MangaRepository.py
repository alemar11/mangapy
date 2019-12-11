import sys

from bs4 import BeautifulSoup
from urllib.request import Request, urlopen
from collections import OrderedDict, namedtuple

class Manga:
    def __init__(self, title, chapters):
        self.title = title
        self.chapters = chapters

    def chapters(self):
        print("chapters")

class Chapter:
    def __init__(self, first_page_url, number):
        self.first_page_url = first_page_url
        self.number = number

    def pages(self):
        return Page("test name", "test url")  

Page = namedtuple("Page", "name url")

class MangaRepository:
    base_url = None

    def search(self, manga):
        print(manga)


def get_page_soup(url):
    """Download a page and return a BeautifulSoup object of the html"""

    request = Request(url)
    request.add_header('User-Agent', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_13_2) AppleWebKit/537.36 \
                              (KHTML, like Gecko) Chrome/63.0.3239.108 Safari/537.36')
    response = urlopen(request, timeout=5)

    if response.info().get('Content-Encoding') == 'gzip':
        gzipFile = gzip.GzipFile(fileobj=response)
        page_content = gzipFile.read()
    else:
        page_content = response.read()

    soup_page = BeautifulSoup(page_content, "html.parser")

    return soup_page


# https://github.com/techwizrd/MangaFox-Download-Script
# https://github.com/jahmad/getmanga/blob/master/getmanga/__init__.py

class MangaFox(MangaRepository):
    name = "MangaFox"
    base_url = "http://fanfox.net"

    def search(self, manga_name):
        manga_url = "{0}/manga/{1}/".format(self.base_url, manga_name)
        soup = get_page_soup(manga_url)

        chapters = soup.find('ul', {'class': 'detail-main-list'}).findAll('a', href=True)

        chapters_url = map(lambda c: c['href'], reversed(chapters))

        _chapters = []

        for url in chapters_url:
            number = url.split("/")[-2][1:] #relative url  
            chapter = Chapter(url, number)
            print(chapter.number) #relative url  
            _chapters.append(chapter)  


        manga = Manga(
            manga_name,
            _chapters
        )


        print(len(manga.chapters))    

        # TODO: manga with multi word titles
        # TODO: @property and static methods

        manga_does_not_exist = soup.find('ul', {'class': 'detail-main-list'})

        if manga_does_not_exist:
            search_sort_options = 'sort=views&order=za'
            url = '{0}/search.php?name={1}&{2}'.format(self.base_url, manga_url, search_sort_options)
            soup = get_page_soup(url)
            results = soup.findAll('a', {'class': 'series_preview'})
            error_text = 'Error: Manga \'{0}\' does not exist'.format(manga_name)
            error_text += '\nDid you meant one of the following?\n  * '
            error_text += '\n  * '.join([manga.text for manga in results][:10])
            sys.exit(error_text)

        warning = soup.find('div', {'class': 'warning'})
        if warning and 'licensed' in warning.text:
            sys.exit('Error: ' + warning.text)


        chapters = OrderedDict()
        links = soup.findAll('a', {'class': 'tips'})
        if(len(links) == 0):
            sys.exit('Error: Manga either does not exist or has no chapters')
        replace_manga_name = re.compile(re.escape(manga_name.replace('_', ' ')),
                                        re.IGNORECASE)

        for link in links:
            chapters[float(replace_manga_name.sub('', link.text).strip())] = link['href']

        ordered_chapters = OrderedDict(sorted(chapters.items()))

        return ordered_chapters

        # prepare the search request
        # execute the request
        # parse list of manga
        
        #print(manga, self._base_url)
        # value stored in a variable 






repository = MangaFox()
repository.search("naruto")
