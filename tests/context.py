import mangapy  # noqa: F401
import os
import sys

# https://docs.python-guide.org/writing/structure/
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# https://hidemy.name/en/proxy-list/?type=hs#list
test_proxies = {'http': 'http://51.38.71.101:8080', 'https': 'https://51.38.71.101:8080'}
