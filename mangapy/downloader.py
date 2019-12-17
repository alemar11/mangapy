import os



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
            os.makedirs(dir, exist_ok=True)
        except OSError as msg:
            raise MangaException(msg)

    file = os.path.join(dir, file_name)
    output = open(file, "wb")
    output.write(data)
    output.close()
    return True