import requests
import os
import glob
from functools import partial
from tqdm import tqdm
from PIL import Image
from urllib.parse import urlparse
from mangapy.mangarepository import Chapter, Page
from mangapy.fanfox import FanFoxRepository, session
from concurrent.futures import ThreadPoolExecutor





class ChapterDownloader2(object):    
    def __init__(self, max_workers=1, session=requests.Session):
        self.max_workers = max_workers
        self.progress_bar = None
        self.session = session

    def fetch(self, url: str):
        response = self.session.get(url)
        if response.status_code != 200:
            return None
        return response.content
            
    def save(self, to: str, page: Page):
        url = page.url
        file_name = str(page.number)
        file_ext = urlparse(url).path.split('.')[-1]
        url = 'http:' + url
        data = self.fetch(url)
        if data is None:
            return
        dir = os.path.expanduser(to)
        if not os.path.isdir(to):
            try:
                os.makedirs(dir, exist_ok=True)
            except OSError as msg:
                print('----')

        file = os.path.join(dir, file_name + '.' + file_ext)
        output = open(file, "wb")
        output.write(data)
        output.close()

    def download(self, chapter: Chapter, to: str):
        to = os.path.join(to, str(chapter.number))
        _pages = chapter.pages()
        description = ('Chapter {0}'.format(str(chapter.number)))
        # currying
        func = partial(self.save, to)
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            list(tqdm(executor.map(func, _pages), total=len(_pages), desc=description, unit='pages', ncols=100))


repo = FanFoxRepository()
manga = repo.search('naruto')
second_ch = manga.chapters[2]
d = ChapterDownloader2(session=session)
d.download(second_ch, '~/Downloads/_mangapy2')            