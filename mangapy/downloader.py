import aiohttp
import glob
import os
from PIL import Image
from urllib.parse import urlparse

class MangaException(Exception):
    """Exception class for manga"""
    pass
  

async def fetch(session: aiohttp.ClientSession, url: str):
    try:
        async with session.get(url) as response:
            if response.status != 200 and response.content is not None:
                return None
            else:    
                return await response.content.read()
    except OSError as msg:
        print(msg)

async def save(session: aiohttp.ClientSession, url: str, path: str, file_name: str):
    file_ext = urlparse(url).path.split('.')[-1]
    data = await fetch(session, url)
    if data is None:
        return
    dir = os.path.expanduser(path)
    if not os.path.isdir(path):
        try:
            os.makedirs(dir, exist_ok=True)
        except OSError as msg:
            raise MangaException(msg)

    file = os.path.join(dir, file_name + '.' + file_ext)
    output = open(file, "wb")
    output.write(data)
    output.close()

def pdf(directory):
    directory = os.path.expanduser(directory)
    search_path = os.path.join(directory, '*.jpg')
    images_path = glob.glob(search_path)
    images_path = natural_sort(images_path)
    images = []
    for path in images_path:
        images.append(Image.open(path))

    pdf_filename = os.path.join(directory, 'chapter.pdf')
    first_image = images.pop(0)
    first_image.save(pdf_filename, "PDF", resolution=100.0, save_all=True, append_images=images)


import re


def natural_sort(list):
    def convert(text):
        return int(text) if text.isdigit() else text.lower()

    def alphanum_key(key):
        return [convert(c) for c in re.split('([0-9]+)', key)]

    return sorted(list, key=alphanum_key)
