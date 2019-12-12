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

        soup.findAll('script', {'type': 'text/javascript'})

        '''
        script text/javascript

                var csshost = "http://static.fanfox.net/v201906282/mangafox/";        
                var comicid = 11529;        
                var chapterid =190399;        
                var userid=0;        
                var imagepage=1;        var imagecount=27;        var pagerrefresh=false;        var pagetype=2;        var postpageindex = 1;        var postpagecount = 0;       
                var postcount=0;        var postsort=0;        var topicId=0;        var prechapterurl="/manga/shokugeki_no_soma/v01/c001/1.html";        
                var nextchapterurl="/manga/shokugeki_no_soma/v01/c003/1.html";    
        '''

        p = re.compile('var comicid = (.*);')
        for script in soup.find_all("script", {"src": False}):
            if script:           
                m = p.search(script.string)
                if m:
                    print(m)
                    #(?<=var comicid = )[0-9]+(?=;)
                    #(?<=var chapterid = )[0-9]+(?=;)
                    #(?<=var imagecount = )[0-9]+(?=;)
                    # https://github.com/Xonshiz/comic-dl/issues/196
                #print(m.group(1))


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

        # http://fanfox.net/manga/gentleman_devil/v03/c038/chapterfun.ashx
        '''
        eval(function(p,a,c,k,e,d){e=function(c){return(c<a?"":e(parseInt(c/a)))+((c=c%a)>35?String.fromCharCode(c+29):c.toString(36))};if(!''.replace(/^/,String)){while(c--)d[e(c)]=k[c]||e(c);k=[function(e){return d[e]}];e=function(){return'\\w+'};c=1;};while(c--)if(k[c])p=p.replace(new RegExp('\\b'+e(c)+'\\b','g'),k[c]);return p;}('r c(){2 h="//s.7.a/e/3/6/4-5.0/b";2 1=["/k.f?g=n&8=9","/l.f?g=m&8=9"];j(2 i=0;i<1.t;i++){u(i==0){1[i]="//s.7.a/e/3/6/4-5.0/b"+1[i];o}1[i]=h+1[i]}p 1}2 d;d=c();q=0;',31,31,'|pvalue|var|manga|01|038|22117|fanfox|ttl|1576252800|net|compressed|dm5imagefun||store|jpg|token|pix||for|e20191002_111418_525|e20191002_111418_526|b4e0963e2a1f126841f25f6aba6d2891f97edf70|8d4f90035f871134e742e2ca4daa7a7438cad7ce|continue|return|currentimageid|function||length|if'.split('|'),0,{}))

        '''

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