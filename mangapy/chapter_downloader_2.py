import requests
import os
import glob
from functools import partial
from tqdm import tqdm
from PIL import Image
from urllib.parse import urlparse
from mangapy.mangarepository import Chapter, Page
from mangapy.fanfox import FanFoxRepository
from concurrent.futures import ThreadPoolExecutor

class ChapterDownloader2(object):    
    session = requests.Session()

    def __init__(self, path: str, max_workers=1):
        self.max_workers = max_workers
        self.path = path

    def _fetch(self, url: str):
        response = self.session.get(url, verify=False)
        if response.status_code != 200:
            return None
        return response.content
            
    def _save(self, to: str, page: Page):
        url = page.url
        file_name = str(page.number)
        file_ext = urlparse(url).path.split('.')[-1]
        if url.startswith('//'):
            url = 'http:' + url
        data = self._fetch(url)
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

    def download(self, chapter: Chapter):
        to = os.path.join(self.path, str(chapter.number))
        pages = chapter.pages()
        description = ('Chapter {0}'.format(str(chapter.number)))
        func = partial(self._save, to) # currying
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            list(tqdm(executor.map(func, pages), total=len(pages), desc=description, unit='pages', ncols=100))

if __name__ == '__main__':
    repo = FanFoxRepository()
    manga = repo.search('naruto')
    second_ch = manga.chapters[3]
    d = ChapterDownloader2('~/Downloads/_mangapy11')
    d.download(second_ch)            