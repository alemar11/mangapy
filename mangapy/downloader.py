import glob
import os
from PIL import Image
from urllib.parse import urlparse

class MangaException(Exception):
    """Exception class for manga"""
    pass
  

async def fetch(session, url):
    try:
        async with session.get(url) as response:
            if response.status != 200 and response.content is not None:
                return None
            else:    
                return await response.content.read()
    except OSError as msg:
        print(msg)


async def save(session, url, path, file_name):
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
    images_path = glob.glob('/Users/amarzoli/Downloads/mangapy/mangapark/naruto/1/*.jpg')
    images = []
    # ---> https://stackoverflow.com/questions/4836710/does-python-have-a-built-in-function-for-string-natural-sort

    for path in images_path:
        print(path)
        images.append(Image.open(path))

    pdf_filename = "/Users/amarzoli/Downloads/mangapy/mangapark/naruto/1/chapter.pdf"

    #os.listdir('/Users/amarzoli/Downloads/mangapy/mangapark/naruto/1/')

    #list = glob.glob('{0}/*.jpg'.format(directory))
    # https://stackoverflow.com/questions/27327513/create-pdf-from-a-list-of-images
    #im1 = Image.open("/Users/apple/Desktop/bbd.jpg")
    #im2 = Image.open("/Users/apple/Desktop/bbd1.jpg")
    #im3 = Image.open("/Users/apple/Desktop/bbd2.jpg")
    #im_list = [im2, im3]
    #pdf1_filename = "/Users/apple/Desktop/bbd1.pdf"
    first_image = images.pop()
    first_image.save(pdf_filename, "PDF", resolution=100.0, save_all=True, append_images=images)