import re
import os

from utils import get_page_soup
from MangaRepository import MangaRepository, Manga, Chapter, Page


class MangaFox(MangaRepository):
    name = "MangaFox"
    base_url = "http://fanfox.net"

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
            print(chapter.number)  # relative url
            manga_chapters.append(chapter)
        
        manga = Manga(
            manga_name,
            manga_chapters
        )
        # TODO: @property and static methods
        return manga


class MangaFoxChapter(Chapter):
    def hello(self):
        print("hello")

    def source(self, page):
        test_url = 'http://fanfox.net/manga/naruto/v01/c000/13.html'
        soup = get_page_soup(test_url)
        #soup.find('img', {'class': 'reader-main-img'})['src']
        print(soup)


    def pages(self):
        #http://fanfox.net/manga/naruto/v72/c700.6/10.html
        #http://fanfox.net/manga/naruto/v01/c000/3.html

        #first_chapter_url = "{0}{1}/".format(self.base_url, self.first_page_url)
        #img class="reader-main-img" src
        soup = get_page_soup(self.first_page_url)
        page_numbers = soup.findAll("a", {"data-page": True})

        page_numbers = map(lambda x: int(x['data-page']), page_numbers)
        first_page_number = 1
        last_page_number = max(page_numbers)

        print(self.source(''))

        pages = []
        for i in range(first_page_number, last_page_number):
            page_url = re.sub(r'(?<=\/)[0-9]+(?=.html)', str(i), self.first_page_url)
            print(page_url)
            page = Page("name", page_url)
            pages.append(page)


repository = MangaFox()

manga = repository.search("naruto")
print(manga.title)
firstChapter = manga.chapters[0]
print(firstChapter.pages())

#repository.search("kimetsu no yaiba")
# test: Kimetsu no Yaiba: Tomioka Giyuu Gaiden

#repository.search('Kimetsu no Yaiba: Tomioka Giyuu Gaiden')


#repository.suggest("kimetsu")
#repository.search('Free! dj - Kekkon Shitara Dou Naru!?') # adult content
#http://fanfox.net/manga/gentleman_devil/v01/c038/1.html # adult content