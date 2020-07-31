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


class MangaDownload:
    def __init__(self, **entries):
        self.__dict__.update(entries)

    def save_as_pdf(self) -> bool:
        if 'pdf' in self.__dict__.keys():
            return self.__dict__['pdf']
        return None

    def download_single(self) -> float:
        if 'download_single_chapter' in self.__dict__.keys():
            return float(self.__dict__['download_single_chapter'].strip())
        return None

    def download_last(self) -> bool:
        if 'download_last_chapter' in self.__dict__.keys():
            return self.__dict__['download_last_chapter']
        return False

    def download_all(self) -> bool:
        if 'download_all_chapters' in self.__dict__.keys():
            return self.__dict__['download_all_chapters']
        return False

    def download_range(self) -> (float, float):
        if 'download_chapters' in self.__dict__.keys():
            chapters = self.__dict__['download_chapters']
            chapters = chapters.split('-')
            begin = None
            end = None
            if len(chapters) == 2:
                begin = float(chapters[0])
                end = float(chapters[1]) if chapters[1] else None
            if begin and end and (float(begin) > float(end)):
                sys.exit('{0}: error: invalid chapter interval, the end should be bigger than start'.format(chapters))
            return begin, end
        return None


def main_yaml(args: argparse.Namespace):
    yaml_file = args.yaml_file.strip()

    try:
        with open(yaml_file, 'r') as f:
            dictionary = yaml.load(f, Loader=yaml.FullLoader)
            output = dictionary['output']

            proxy = None
            if 'proxy' in dictionary.keys() and dictionary['proxy']:
                proxy_info = dictionary['proxy']
                if 'http' and 'https' in proxy_info.keys():
                    print('Setting proxy')
                    proxy = dictionary['proxy']
                else:
                    print('The proxy is not in the right format and it will not be used.')

            debug_log = False
            if 'debug' in dictionary.keys() and dictionary['debug']:
                debug_log = True

            if 'fanfox' in dictionary.keys():
                for download in list(map(lambda manga: MangaDownload(**manga), dictionary['fanfox'])):
                    download.source = 'fanfox'
                    download.enable_debug_log = debug_log
                    download.output = output
                    download.proxy = proxy
                    start_download(download)
            
            if 'mangapark' in dictionary.keys():
                for download in list(map(lambda manga: MangaDownload(**manga), dictionary['mangapark'])):
                    download.source = 'mangapark'
                    download.enable_debug_log = debug_log
                    download.output = output
                    download.proxy = proxy
                    start_download(download)
    except Exception as error:   
        print(error)


def main_title(args: argparse.Namespace):
    download = MangaDownload()
    download.title = args.manga_title.strip()
    download.output = args.out.strip()
    download.pdf = args.pdf or False
    source = args.source

    if args.debug:
        download.enable_debug_log = True
    else:
        download.enable_debug_log = False

    if source is None:
        download.source = 'fanfox'
    else:
        download.source = source.strip().lower()

    download.proxy = None
    if args.proxy:
        if 'http' and 'https' in args.proxy.keys():
            print('Setting proxy')
            download.proxy = args.proxy
        else:
            print('The proxy is not in the right format and it will not be used.')
            
    if args.all:
        download.download_all_chapters = True

    elif args.chapter:
        chapters = args.chapter.split('-')
        if len(chapters) == 2:
            download.download_chapters = args.chapter
        else:
            download.download_single_chapter = args.chapter.strip()
    else:
        download.download_last_chapter = True

    start_download(download)


def start_download(download: MangaDownload):
    if download.enable_debug_log:
        log.setLevel(logging.DEBUG)
    else:
        log.setLevel(logging.ERROR)

    if download.source is None:
        repository = FanFoxRepository()
        repository_directory = 'fanfox'
        max_workers = 1  # to avoid bot detection
    else:
        source = download.source.strip().lower()
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

    if download.proxy:
        repository.proxies = download.proxy

    print('🔎  Searching for {0} in {1}...'.format(download.title, download.source))
    try:
        manga = repository.search(download.title)
    except Exception as e:
        logging.error(str(e))
        return

    if manga is None or len(manga.chapters) <= 0:
        print('❌  Manga {0} doesn\'t exist.'.format(download.title))
        return

    print('✅  {0} found'.format(manga.title))
    directory = os.path.join(download.output, repository_directory, manga.subdirectory)
    chapters = []

    if download.download_all():
        chapters = manga.chapters

    elif download.download_single() is not None:
        download_chapter = download.download_single()
        for chapter in manga.chapters:
            if chapter.number == download_chapter:
                chapters.append(chapter)
                break
        else:
            logging.error("❌  Chapter doesn't exist.")
            return

    elif download.download_range() is not None:
        range = download.download_range()
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

    print('⬇️  Download started.')
    archiver = ChapterArchiver(directory, max_workers=max_workers)
    for chapter in chapters:
        try:
            archiver.archive(chapter, download.save_as_pdf())
        except Exception as e:
            logging.error(str(e))

    print('🎉  Download finished.')


if __name__ == '__main__':
    main_folder = os.getcwd()
    yaml_file = os.path.join(main_folder, 'sample3.yaml')
    sys.argv.insert(1, 'yaml')
    sys.argv.insert(2, yaml_file)

    # sys.argv.insert(1, 'title')
    # sys.argv.insert(2, 'jujutsu kaisen')
    # sys.argv.insert(3, '-o ~/Downloads/mangapy_test')
    # sys.argv.insert(4, '-c 1-100')
    # sys.argv.insert(5, '-s mangapark')
    # sys.argv.insert(6, '--pdf')
    # sys.argv.insert(7, '--debug')
    # sys.argv.insert(8, '-p {"http": "http://31.14.131.70:8080", "https": "http://31.14.131.70:8080"}')

    main()
