import re
import os
import gzip

from utils import get_page_soup
from MangaRepository import MangaRepository, Manga, Chapter, Page
from collections import namedtuple
import urllib.request

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
            manga_chapters.append(chapter)
        
        manga = Manga(
            manga_name,
            manga_chapters
        )
        # TODO: @property and static methods
        return manga


ChapterMetadata = namedtuple("ChapterMetadata", "comic_id chapter_id image_count")

class MangaFoxChapter(Chapter):
    def hello(self):
        print("hello")

    def metadata(self, page):
        test_url = 'http://fanfox.net/manga/naruto/v01/c000/13.html'
        soup = get_page_soup(test_url)

        comic_id = None
        chapter_id = None
        image_count = None

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

        if comic_id is None or chapter_id is None or image_count is None:
            return None

        return ChapterMetadata(comic_id, chapter_id, int(image_count))
                    


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

        metadata = self.metadata(self.first_page_url)

        # http://fanfox.net/manga/gentleman_devil/v03/c038/chapterfun.ashx

        # http://fanfox.net/manga/naruto/v72/c000/1.html
        # http://fanfox.net/manga/naruto/v72/c700.6/chapterfun.ashx?cid=370505&page=1&key=

        # chapter id 37505

        _request = urllib.request.Request(self.first_page_url)
        _request.add_header('User-Agent', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_13_2) AppleWebKit/537.36 \
                              (KHTML, like Gecko) Chrome/63.0.3239.108 Safari/537.36')
        _r = urllib.request.urlopen(_request)

        url = self.first_page_url[:self.first_page_url.rfind('/')]
        url += '/chapterfun.ashx?cid={0}&page={1}&key='.format(metadata.chapter_id, 1)
        

        url = 'http://fanfox.net/manga/naruto/v72/c700.6/chapterfun.ashx?cid=370505&page=1&key='

        request = urllib.request.Request(url)
        request.add_header('User-Agent', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_13_2) AppleWebKit/537.36 \
                              (KHTML, like Gecko) Chrome/63.0.3239.108 Safari/537.36')


        #curl "http://fanfox.net/manga/naruto/v72/c700.6/chapterfun.ashx?cid=370505&page=3&key=5a79d5696ec4d773" -H "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:63.0) Gecko/20100101 Firefox/63.0"                      

        #request.add_header('Cookie', '__cfduid=d0f0db9991e529488e861d4d2b86a96aa1576244331; DM5_MACHINEKEY=4ba3098c-972a-49ff-a4ed-28cb0fa01ffc; SERVERID=node1; UM_distinctid=16eff7bc346105-0963b5e11a3526-12326b5a-384000-16eff7bc347f09; CNZZDATA1278094021=131635546-1576242533-%7C1576242533; CNZZDATA1278094028=1526391161-1576242090-%7C1576242090; __utma=1.1523059990.1576244331.1576244331.1576244331.1; __utmc=1; __utmz=1.1576244331.1.1.utmcsr=(direct)|utmccn=(direct)|utmcmd=(none); image_time_cookie=370505|637118699314357798|0; dm5imgpage=370505|1:0; readhistoryitem=History=8,637118699314514387,370505,1,0,0,0,750&ViewType=0; readhistory_time=8-370505-1; imageload=370505%7C2; __utmb=1.2.10.1576244331')
        #request.add_header('Cookie', '__cfduid=d0f0db9991e529488e861d4d2b86a96aa1576244331; DM5_MACHINEKEY=4ba3098c-972a-49ff-a4ed-28cb0fa01ffc; SERVERID=node1; UM_distinctid=16eff7bc346105-0963b5e11a3526-12326b5a-384000-16eff7bc347f09; CNZZDATA1278094021=131635546-1576242533-%7C1576242533; CNZZDATA1278094028=1526391161-1576242090-%7C1576242090; __utma=1.1523059990.1576244331.1576244331.1576244331.1; __utmc=1; __utmz=1.1576244331.1.1.utmcsr=(direct)|utmccn=(direct)|utmcmd=(none); dm5imgpage=370505|1:0; readhistory_time=8-370505-1; imageload=370505%7C2; __utmb=1.3.10.1576244331; image_time_cookie=370505|637118729348173275|4; readhistoryitem=History=8,637118706252704366,370505,1,0,0,0,750&ViewType=0')
        request.add_header('Cookie', 'image_time_cookie=370505|637118729348173275|4;')
        response = urllib.request.urlopen(request, timeout=5)
        content = response.read()

        body = content
        body = body.decode().rstrip("\n\r")

        encrypted = body.split('}(')[1][:-1]
        print(eval('unpack(' + encrypted))

        pages = []
        for i in range(first_page_number, last_page_number): # TODO this not consider the last page
            page_url = re.sub(r'(?<=\/)[0-9]+(?=.html)', str(i), self.first_page_url)
            print(page_url)
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




#encrypted = r'''eval(function(p,a,c,k,e,d){e=function(c){return c};if(!''.replace(/^/,String)){while(c--)d[c]=k[c]||c;k=[function(e){return d[e]}];e=function(){return'\\w+'};c=1;};while(c--)if(k[c])p=p.replace(new RegExp('\\b'+e(c)+'\\b','g'),k[c]);return p;}('5 11=17;5 12=["/3/2/1/0/13.4","/3/2/1/0/15.4","/3/2/1/0/14.4","/3/2/1/0/7.4","/3/2/1/0/6.4","/3/2/1/0/8.4","/3/2/1/0/10.4","/3/2/1/0/9.4","/3/2/1/0/23.4","/3/2/1/0/22.4","/3/2/1/0/24.4","/3/2/1/0/26.4","/3/2/1/0/25.4","/3/2/1/0/18.4","/3/2/1/0/16.4","/3/2/1/0/19.4","/3/2/1/0/21.4"];5 20=0;',10,27,'40769|54|Images|Files|png|var|imanhua_005_140430179|imanhua_004_140430179|imanhua_006_140430226|imanhua_008_140430242|imanhua_007_140430226|len|pic|imanhua_001_140429664|imanhua_003_140430117|imanhua_002_140430070|imanhua_015_140430414||imanhua_014_140430382|imanhua_016_140430414|sid|imanhua_017_140430429|imanhua_010_140430289|imanhua_009_140430242|imanhua_011_140430367|imanhua_013_140430382|imanhua_012_140430367'.split('|'),0,{}))'''
encrypted = r'''eval(function(p,a,c,k,e,d){e=function(c){return(c<a?"":e(parseInt(c/a)))+((c=c%a)>35?String.fromCharCode(c+29):c.toString(36))};if(!''.replace(/^/,String)){while(c--)d[e(c)]=k[c]||e(c);k=[function(e){return d[e]}];e=function(){return'\\w+'};c=1;};while(c--)if(k[c])p=p.replace(new RegExp('\\b'+e(c)+'\\b','g'),k[c]);return p;}('r c(){2 h="//s.7.a/e/3/6/4-5.0/b";2 1=["/k.f?g=n&8=9","/l.f?g=m&8=9"];j(2 i=0;i<1.t;i++){u(i==0){1[i]="//s.7.a/e/3/6/4-5.0/b"+1[i];o}1[i]=h+1[i]}p 1}2 d;d=c();q=0;',31,31,'|pvalue|var|manga|01|038|22117|fanfox|ttl|1576252800|net|compressed|dm5imagefun||store|jpg|token|pix||for|e20191002_111418_525|e20191002_111418_526|b4e0963e2a1f126841f25f6aba6d2891f97edf70|8d4f90035f871134e742e2ca4daa7a7438cad7ce|continue|return|currentimageid|function||length|if'.split('|'),0,{}))'''
encrypted = encrypted.split('}(')[1][:-1]
print(eval('unpack(' + encrypted))