import requests
from bs4 import BeautifulSoup


class Proxy:
    checked_url = 'https://httpbin.org/ip'

    @staticmethod
    def __strip(text):
        return text.text.strip(' \n\t\r\0')

    def _s(self, item):
        td = item.select('td')
        proxy = self.__strip(td[4])  # proxy type
        https = self.__strip(td[6])  # https (yes|no)
        if (proxy == 'anonymous' or proxy == 'elite proxy') and https == 'yes':
            return self.__strip(td[0]) + ':' + self.__strip(td[1])
        return None

    def _test_proxy(self, url):
        proxies = {
            'http': url,
            'https': url,
        }
        try:
            requests.head(url=self.checked_url, proxies=proxies, timeout=6)
        except Exception:
            return False
        return proxies

    def _change_checked_url(self, checked_url):
        if checked_url:
            self.checked_url = checked_url

    def auto_proxy(self, checked_url=None):
        self._change_checked_url(checked_url)
        url = 'https://www.us-proxy.org'
        content = requests.get(url).text
        soup = BeautifulSoup(content, features="html.parser")
        items = soup.select('#proxylisttable tbody tr')
        for n, i in enumerate(items):
            proxy = self._s(i)
            test = False
            if proxy:
                test = self._test_proxy(proxy)
            if test:
                return test
        return None


if __name__ == '__main__':
    print(Proxy().auto_proxy('http://fanfox.net'))