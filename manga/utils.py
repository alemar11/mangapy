from bs4 import BeautifulSoup
from urllib.request import Request, urlopen

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


