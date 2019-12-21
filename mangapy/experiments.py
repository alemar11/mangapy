from concurrent import futures
import asyncio
import time
import requests


# test how to define a coroutine

'''
loop = asyncio.get_event_loop()

async def task(t):
    print('start task(%d)'%t)
    time.sleep(5)
    print('finish task(%d)'%t)

async def main(loop):
    futures = []
    for i in range(1, 4):
        futures.append(loop.create_task(task(i)))
    await asyncio.gather(*futures)

try:
    loop.run_until_complete(main(loop))
except:
    loop.close()
'''

import asyncio
from random import randint


async def download(code):
    wait_time = randint(1, 3)
    print('downloading {} will take {} second(s)'.format(code, wait_time))
    await asyncio.sleep(wait_time)  # I/O, context will switch to main function
    print('downloaded {}'.format(code))

async def safe_download(i, sem):
    async with sem:  # semaphore limits num of simultaneous downloads
        return await download(i)

async def main():
    sem = asyncio.Semaphore(3)
    tasks = [
        asyncio.ensure_future(safe_download(i, sem))  # creating task starts coroutine
        for i
        in range(9)
    ]
    await asyncio.gather(*tasks)  # await moment all downloads done


if __name__ ==  '__main__':
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(main())
    finally:
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()    