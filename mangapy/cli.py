import asyncio
import sys
import pkg_resources
import argparse
import os

from mangapy.mangapark import MangaParkRepository
from mangapy.mangarepository import download


version = pkg_resources.require("mangapy")[0].version


def cmdparse():
    """Returns parsed arguments from command line"""
    parser = argparse.ArgumentParser()
    parser.add_argument('title', type=str, help="manga title to download")
   
    group = parser.add_mutually_exclusive_group()
    group.add_argument('-a', '--all', action='store_true', help="download all chapters available")
    group.add_argument('-c', '--chapter', type=str, help="chapter(s) number to download")
    parser.add_argument('-d', '--dir', type=str, default='.', help='download directory')
    parser.add_argument('-v', '--version', action='version',
                        version='{0} {1}'.format(parser.prog, version),
                        help="show program version and exit")

    args = parser.parse_args()
    args.begin = None
    args.end = None

    if args.chapter:
        chapter = args.chapter.split('-')
        if len(chapter) == 2:
            args.chapter = None
            args.begin = chapter[0]
            args.end = chapter[1] if chapter[1] else None
        if args.begin and args.end and (int(args.begin) > int(args.end)):
            parser.print_usage()
            sys.exit("{0}: error: invalid chapter interval, the end "
                     "should be bigger than start".format(parser.prog))
    return args


def main():
    args = cmdparse()
    title = args.title.strip()
    directory = args.dir.strip()

    repository = MangaParkRepository()
    manga = repository.search(title)
    directory = os.path.join(directory, 'mangapark', manga.subdirectory)
    tasks = []

    if manga is None or len(manga.chapters) <= 0:
        return

    if args.all:
        for chapter in manga.chapters:
            tasks.append(download(chapter, directory))
    elif args.chapter:
        try:
            chapter_number = int(args.chapter.strip())
        except ValueError:
            sys.exit("Invalid chapter number.")

        for chapter in manga.chapters:
            if chapter.number == chapter_number:
                tasks.append(download(chapter, directory))
                break
        else:
            sys.exit("Chapter doesn't exist.")

    elif args.begin:
        start = None
        stop = None
        for index, chapter in enumerate(manga.chapters):
            if chapter.number == args.begin:
                start = index
            if args.end and chapter.number == args.end:
                stop = index + 1
        for chapter in manga.chapters[start:stop]:
            # TODO: test
            tasks.append(download(chapter, directory))

    else:
        last_chapter = manga.chapters[-1]
        tasks.append(download(last_chapter, directory))

    #loop = asyncio.new_event_loop()
    #asyncio.set_event_loop(loop)
    loop = asyncio.get_event_loop()
    #https://www.educative.io/blog/python-concurrency-making-sense-of-asyncio 
    loop.run_until_complete(asyncio.wait(tasks))
    loop.close()


if __name__ == '__main__':
    #sys.argv.insert(1, "Naruto - Eroi no Vol.1 (Doujinshi)")
    sys.argv.insert(1, "bleach")
    sys.argv.insert(2, "-d ~/Downloads/mangapy")
    sys.argv.insert(2, "-c 2")
    main()
