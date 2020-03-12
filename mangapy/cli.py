import argparse
import yaml
import json
import logging
import os
import pkg_resources
import sys
from mangapy.mangapark import MangaParkRepository
from mangapy.fanfox import FanFoxRepository
from mangapy.chapter_archiver import ChapterArchiver
from mangapy import log
from pathlib import Path


version = pkg_resources.require("mangapy")[0].version
default_path_to_download_folder = str(os.path.join(Path.home(), "Downloads", "mangapy"))


def cmd_parse():
    """Returns parsed arguments from command line"""
    parser = argparse.ArgumentParser()

    subparsers = parser.add_subparsers(help='Download modes.', dest='mode')

    yaml_parser = subparsers.add_parser("yaml")
    args_parser = subparsers.add_parser("title")

    yaml_parser.add_argument('yaml_file', type=str, help="Path to the .yaml file")

    args_parser.add_argument('manga_title', type=str, help="manga title to download")
    args_parser.add_argument('-s', '--source', type=str, help="manga source")
    args_parser.add_argument('-o', '--out', type=str, default=default_path_to_download_folder, help='download directory')
    args_parser.add_argument('-d', '--debug', action='store_true', help="set log to DEBUG level")
    args_parser.add_argument('--pdf', action='store_true', help="create a pdf for each chapter")

    args_parser.add_argument('-p', '--proxy', type=json.loads, help="use a proxy to download the chapters")
    group = args_parser.add_mutually_exclusive_group()
    group.add_argument('-a', '--all', action='store_true', help="download all chapters available")
    group.add_argument('-c', '--chapter', type=str, help="chapter(s) number to download")
    
    parser.add_argument('-v', '--version',
                        action='version',
                        version='{0} {1}'.format(parser.prog, version),
                        help="show program version and exit")

    args = parser.parse_args()
    return args


def main():
    args = cmd_parse()
    if args.mode == 'title':
        main_title(args)
    elif args.mode == 'yaml':
        main_yaml(args)


class MangaRepo:
    def __init__(self, **entries):
        self.__dict__.update(entries)

    def _pdf(self) -> bool:
        if 'pdf' in self.__dict__.keys():
            return self.__dict__['pdf']
        return None

    def _download_chapter(self) -> float:
        if 'download_chapter' in self.__dict__.keys():
            return float(self.__dict__['download_chapter'].strip())
        return None

    def _download_last(self) -> bool:
        if 'download_last' in self.__dict__.keys():
            return self.__dict__['download_last']
        return False

    def _download_all(self) -> bool:
        if 'download_all' in self.__dict__.keys():
            return self.__dict__['download_all']
        return False

    def _download_chapters(self) -> (int, int):
        if 'download_chapters' in self.__dict__.keys():
            chapters = self.__dict__['download_chapters']
            chapters = chapters.split('-')
            begin = None
            end = None
            if len(chapters) == 2:
                begin = int(chapters[0])
                end = int(chapters[1]) if chapters[1] else None
            if begin and end and (int(begin) > int(end)):
                sys.exit('{0}: error: invalid chapter interval, the end should be bigger than start'.format(chapters))
            return begin, end
        return None


def main_yaml(args: argparse.Namespace):
    yaml_file = args.yaml_file.strip()

    with open(yaml_file, 'r') as f:
        dictionary = yaml.load(f, Loader=yaml.FullLoader)
        output = dictionary['output']

        if 'debug' in dictionary.keys() and dictionary['debug']:
            log.setLevel(logging.DEBUG)
        else:
            log.setLevel(logging.ERROR)

        if 'fanfox' in dictionary.keys():
            for manga_data in list(map(lambda manga: MangaRepo(**manga), dictionary['fanfox'])):
                main_common(manga_data, output, None, 'fanfox')
        
        if 'mangapark' in dictionary.keys():
            for manga in list(map(lambda manga: MangaRepo(**manga), dictionary['mangapark'])):
                print(manga._download_chapters())


def main_common(manga_data: MangaRepo, directory: str, proxy, source):
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

    if proxy:
        if 'http' and 'https' in proxy.keys():
            print('Setting proxy')
            repository.proxies = proxy
        else:
            print('The proxy is not in the right format and it will not be used.')

    print('🔎  Searching for {0}...'.format(manga_data.title))
    try:
        manga = repository.search(manga_data.title)
    except Exception as e:
        logging.error(str(e))
        return

    if manga is None or len(manga.chapters) <= 0:
        print('❌  Manga {0} doesn\'t exist.'.format(manga_data.title))
        return

    print('✅  {0} found'.format(manga.title))
    directory = os.path.join(directory, repository_directory, manga.subdirectory)
    chapters = []

    if manga_data._download_all():
        chapters = manga.chapters

    elif manga_data._download_chapter() is not None:
        download_chapter = manga_data._download_chapter()
        for chapter in manga.chapters:
            if chapter.number == download_chapter:
                chapters.append(chapter)
                break
        else:
            logging.error("❌  Chapter doesn't exist.")
            return

    elif manga_data._download_chapters() is not None:
        range = manga_data._download_chapters()
        range_begin = range[0]
        range_end = range[1]
        start = None
        stop = None
        for index, chapter in enumerate(manga.chapters):
            if chapter.number == range_begin:
                start = index
            if range_end and chapter.number == range_end:
                stop = index + 1
        for chapter in manga.chapters[start:stop]:
            chapters.append(chapter)
 
    else:  # manga._download_last()
        last_chapter = manga.last_chapter
        chapters.append(last_chapter)

    print('⬇️  Downloading...')
    archiver = ChapterArchiver(directory, max_workers=max_workers)
    for chapter in chapters:
        try:
            archiver.archive(chapter, manga_data._pdf())
        except Exception as e:
            logging.error(str(e))

    print('Download finished 🎉🎉🎉')


def main_title(args: argparse.Namespace):
    manga_title = args.manga_title.strip()
    directory = args.out.strip()
    source = args.source

    args.begin = None
    args.end = None

    if args.chapter:
        chapter = args.chapter.split('-')
        if len(chapter) == 2:
            args.chapter = None
            args.begin = int(chapter[0])
            args.end = int(chapter[1]) if chapter[1] else None
        if args.begin and args.end and (int(args.begin) > int(args.end)):
            sys.exit('Invalid chapter interval, the end ({0}) should be bigger than start ({1})'.format(args.end, args.begin))

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

    print('🔎 Searching for {0}...'.format(manga_title))
    try:
        manga = repository.search(manga_title)
    except Exception as e:
        logging.error(str(e))
        sys.exit(str(e))

    if manga is None or len(manga.chapters) <= 0:
        sys.exit('Manga {0} doesn\'t exist.'.format(manga_title))

    print('✅  {0} found'.format(manga_title))
    directory = os.path.join(directory, repository_directory, manga.subdirectory)
    chapters = []

    if args.all:
        chapters = manga.chapters

    elif args.chapter:
        try:
            chapter_number = float(args.chapter.strip())
        except ValueError:
            sys.exit("❌  Invalid chapter number.")

        for chapter in manga.chapters:
            if chapter.number == chapter_number:
                chapters.append(chapter)
                break
        else:
            sys.exit("❌  Chapter doesn't exist.")

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

    print('⬇️  Downloading...')
    archiver = ChapterArchiver(directory, max_workers=max_workers)
    for chapter in chapters:
        try:
            archiver.archive(chapter, args.pdf)
        except Exception as e:
            logging.error(str(e))

    print('Download finished 🎉🎉🎉')


if __name__ == '__main__':
    current_folder = os.path.dirname(os.path.abspath(__file__))
    yaml_file = os.path.join(current_folder, 'test.yaml')

    sys.argv.insert(1, 'yaml')
    sys.argv.insert(2, yaml_file)

    # sys.argv.insert(1, 'title')
    # sys.argv.insert(2, 'bleach')
    # sys.argv.insert(3, '-o ~/Downloads/mangapy_test')
    # #sys.argv.insert(4, '-c 0-1')
    # sys.argv.insert(4, '-c 428.1')
    # #sys.argv.insert(5, '-s mangapark')
    # sys.argv.insert(6, '--pdf')
    # # sys.argv.insert(7, '-p {"http": "194.226.34.132:8888", "https": "194.226.34.132:8888"}')

    main()
