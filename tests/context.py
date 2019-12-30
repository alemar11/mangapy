import mangapy  # noqa: F401
import os
import sys

# https://docs.python-guide.org/writing/structure/
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# https://hidemy.name/en/proxy-list/?type=hs#list
test_proxies = {'http': '194.226.34.132:8888', 'https': '194.226.34.132:8888'}
