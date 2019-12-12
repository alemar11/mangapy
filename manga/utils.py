import urllib.request

from bs4 import BeautifulSoup
from gzip import GzipFile


def get_page_soup(url):
    """Download a page and return a BeautifulSoup object of the html"""
    request = urllib.request.Request(url)
    request.add_header('User-Agent', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_13_2) AppleWebKit/537.36 \
                              (KHTML, like Gecko) Chrome/63.0.3239.108 Safari/537.36')

    request.add_header('Cookie', 'isAdult=1')
    response = urllib.request.urlopen(request, timeout=5)

    # https://free-proxy-list.net
    #request.set_proxy('91.203.27.139', 'https')
    #had_proxy = request.has_proxy()

    if response.info().get('Content-Encoding') == 'gzip':
        gzipFile = GzipFile(fileobj=response)
        page_content = gzipFile.read()
    else:
        page_content = response.read()

    soup = BeautifulSoup(page_content, "html.parser")
    return soup
