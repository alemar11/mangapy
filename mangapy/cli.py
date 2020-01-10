import argparse
import json
import logging
import os
import pkg_resources
import sys
from mangapy.mangapark import MangaParkRepository
from mangapy.fanfox import FanFoxRepository
from mangapy.chapter_archiver import ChapterArchiver
from mangapy import log

version = pkg_resources.require("mangapy")[0].version


def cmd_parse():
    """Returns parsed arguments from command line"""
    parser = argparse.ArgumentParser()
    parser.add_argument('title', type=str, help="manga title to download")
    parser.add_argument('-s', '--source', type=str, help="manga source")
    parser.add_argument('-o', '--out', type=str, default='.', help='download directory', required=True)
    parser.add_argument('-d', '--debug', action='store_true', help="set log to DEBUG level")
    parser.add_argument('--pdf', action='store_true', help="create a pdf for each chapter")

    parser.add_argument('-p', '--proxy', type=json.loads, help="use a proxy to download the chapters")
    group = parser.add_mutually_exclusive_group()
    group.add_argument('-a', '--all', action='store_true', help="download all chapters available")
    group.add_argument('-c', '--chapter', type=str, help="chapter(s) number to download")
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
            sys.exit('{0}: error: invalid chapter interval, the end '
                     'should be bigger than start'.format(parser.prog))
    return args


def main():
    args = cmd_parse()
    title = args.title.strip()
    directory = args.out.strip()
    source = args.source

    if args.debug:
        log.setLevel(logging.DEBUG)
    else:
        log.setLevel(logging.ERROR)

    if source is None:
        repository = FanFoxRepository()
        repository_directory = 'fanfox'
        max_workers = 1  # to avoid bot detection
    else:
        source = source.strip().lower()
        if source == 'fanfox':
            repository = FanFoxRepository()
            repository_directory = source
            max_workers = 1  # to avoid bot detection
        elif source == 'mangapark':
            repository = MangaParkRepository()
            repository_directory = source
            max_workers = 5
        else:
            sys.exit('source is missing')

    if args.proxy:
        if 'http' and 'https' in args.proxy.keys():
            print('Setting proxy')
            repository.proxies = args.proxy
        else:
            print('The proxy is not in the right format and it will not be used.')

    print('🔎 Searching for {0}...'.format(title))
    try:
        manga = repository.search(title)
    except Exception as e:
        logging.error(str(e))
        sys.exit(str(e))

    if manga is None or len(manga.chapters) <= 0:
        sys.exit('Manga {0} doesn\'t exist.'.format(title))

    print('✅ {0} found'.format(title))
    directory = os.path.join(directory, repository_directory, manga.subdirectory)
    chapters = []

    if args.all:
        chapters = manga.chapters

    elif args.chapter:
        try:
            chapter_number = float(args.chapter.strip())
        except ValueError:
            sys.exit("❌ Invalid chapter number.")

        for chapter in manga.chapters:
            if chapter.number == chapter_number:
                chapters.append(chapter)
                break
        else:
            sys.exit("❌ Chapter doesn't exist.")

    elif args.begin is not None and args.begin >= 0:
        start = None
        stop = None
        for index, chapter in enumerate(manga.chapters):
            if chapter.number == args.begin:
                start = index
            if args.end and chapter.number == args.end:
                stop = index + 1
        for chapter in manga.chapters[start:stop]:
            chapters.append(chapter)

    else:
        last_chapter = manga.last_chapter
        chapters.append(last_chapter)

    print('⬇️ Downloading...')
    archiver = ChapterArchiver(directory, max_workers=max_workers)
    for chapter in chapters:
        try:
            archiver.archive(chapter, args.pdf)
        except Exception as e:
            logging.error(str(e))

    print('Download finished 🎉🎉🎉')


if __name__ == '__main__':
    sys.argv.insert(1, 'bleach')
    sys.argv.insert(2, '-o ~/Downloads/mangapy_test')
    #sys.argv.insert(3, '-c 0-1')
    sys.argv.insert(3, '-c 428.1')
    #sys.argv.insert(4, '-s mangapark')
    sys.argv.insert(5, '--pdf')
    # sys.argv.insert(6, '-p {"http": "194.226.34.132:8888", "https": "194.226.34.132:8888"}')
    main()
