import mangapy  # noqa: F401
import os
import sys


sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


# https://docs.python-guide.org/writing/structure/

# https://hidemy.name/en/proxy-list/?type=hs#list
test_proxies = {'http': '5.135.182.93:3128', 'https': '5.135.182.93:3128'}
