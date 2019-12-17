import os
import asyncio
import aiohttp
import hashlib


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
    data = await fetch(session, url)
    if data is None:
        return False
    dir = os.path.expanduser(path)
    os.makedirs(dir, exist_ok=True)
    if not os.path.isdir(path):
        try:
            os.makedirs(path, exist_ok=True)
        except OSError as msg:
            raise MangaException(msg)

    file = os.path.join(dir, file_name)
    output = open(file, "wb")
    output.write(data)
    output.close()
    return True     


async def main():
    urls = [
            'https://z-img-04.mangapark.net/images/dc/12/dc12c6e7e79cfb92f0a63730c7a65c2a9c497c6d_110113_684_1100.jpg',
            #'https://www.go_ogle.com',
        ]
    tasks = []
    async with aiohttp.ClientSession() as session:
        for url in urls:
            hash_object = hashlib.md5(url.encode())
            digest = hash_object.hexdigest()
            tasks.append(save(session, url, '~/Downloads/ale_test2', digest))
        contents = await asyncio.gather(*tasks)
        for content in contents:
            print(content)

if __name__ == '__main__':
    urls = [
        #'https://z-img-04.mangapark.net/images/dc/12/dc12c6e7e79cfb92f0a63730c7a65c2a9c497c6d_110113_684_1100.jpg',
        #'https://z-img-04.mangapark.net/images/d1/8f/d18f1a49e77484bd7bd25115e2e306af9927028b_54387_618_1100.jpg',
        ]
    dir_path = '~/Downloads/ale_test2'   

    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())


'''
if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    url = 'https://z-img-04.mangapark.net/images/dc/12/dc12c6e7e79cfb92f0a63730c7a65c2a9c497c6d_110113_684_1100.jpg'
    url2 = 'https://z-img-04.mangapark.net/images/d1/8f/d18f1a49e77484bd7bd25115e2e306af9927028b_54387_618_1100.jpg'
    #download(url, '~/Downloads/ale_test', "file.jpg") 
    session = requests.Session()  
    future = asyncio.ensure_future(save(url, session, '~/Downloads/ale_test', "file1.jpg"))
    loop.run_until_complete(future)
'''