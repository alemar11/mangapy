import sys
import pkg_resources
import argparse
import os

from mangapy.mangarepository import Chapter
from mangapy.mangapark import MangaParkRepository
from mangapy.fanfox import FanFoxRepository
from mangapy.chapter_downloader_2 import ChapterDownloader2
from threading import Thread, Semaphore


version = pkg_resources.require("mangapy")[0].version


def cmdparse():
    """Returns parsed arguments from command line"""
    parser = argparse.ArgumentParser()
    parser.add_argument('title', type=str, help="manga title to download")
    group = parser.add_mutually_exclusive_group()
    group.add_argument('-a', '--all', action='store_true', help="download all chapters available")
    group.add_argument('-c', '--chapter', type=str, help="chapter(s) number to download")
    parser.add_argument('-d', '--dir', type=str, default='.', help='download directory')
    parser.add_argument('-v', '--version',
                        action='version',
                        version='{0} {1}'.format(parser.prog, version),
                        help="show program version and exit")

    args = parser.parse_args()
    args.begin = None
    args.end = None

    if args.chapter:
        chapter = args.chapter.split('-')
        if len(chapter) == 2:
            args.chapter = None
            args.begin = int(chapter[0])
            args.end = int(chapter[1]) if chapter[1] else None
        if args.begin and args.end and (int(args.begin) > int(args.end)):
            parser.print_usage()
            sys.exit("{0}: error: invalid chapter interval, the end "
                     "should be bigger than start".format(parser.prog))
    return args


def main():
    args = cmdparse()
    title = args.title.strip()
    directory = args.dir.strip()

    #repository = MangaParkRepository()
    repository = FanFoxRepository()
    manga = repository.search(title)
    directory = os.path.join(directory, 'mangapark', manga.subdirectory)
    chapters = []

    if manga is None or len(manga.chapters) <= 0:
        return

    if args.all:
        chapters = manga.chapters
    elif args.chapter:
        try:
            chapter_number = int(args.chapter.strip())
        except ValueError:
            sys.exit("Invalid chapter number.")

        for chapter in manga.chapters:
            if chapter.number == chapter_number:
                chapters.append(chapter)
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
            chapters.append(chapter)

    else:
        last_chapter = manga.chapters[-1]
        chapters.append(last_chapter)

    [schedule(chapter, directory) for chapter in chapters]


def schedule(chapter: Chapter, directory: str):
    cd = ChapterDownloader2(directory, max_workers=1) #it should be one for fanfox
    cd.download(chapter=chapter)


if __name__ == '__main__':
    #sys.argv.insert(1, "Naruto - Eroi no Vol.1 (Doujinshi)")
    sys.argv.insert(1, "bleach")
    sys.argv.insert(2, "-d ~/Downloads/mangapy")
    #sys.argv.insert(2, "-c 11")
    sys.argv.insert(2, "-c 11-32")
    main()
