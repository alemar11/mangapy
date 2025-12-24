import argparse
import yaml
import json
import importlib.metadata
import os
import sys
from mangapy.download_manager import DownloadManager, DownloadRequest
from pathlib import Path

try:
    version = importlib.metadata.version('mangapy')
except importlib.metadata.PackageNotFoundError:
    version = '0.0.0'
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
    try:
        args = cmd_parse()
        if args.mode == 'title':
            main_title(args)
        elif args.mode == 'yaml':
            main_yaml(args)
    except KeyboardInterrupt:
        print("\n⛔️  Download canceled by user.")
        sys.exit(130)


def main_yaml(args: argparse.Namespace):
    yaml_file = args.yaml_file.strip()

    try:
        with open(yaml_file, 'r') as f:
            dictionary = yaml.load(f, Loader=yaml.FullLoader)
            output = dictionary.get('output', default_path_to_download_folder)

            proxy = None
            if 'proxy' in dictionary.keys() and dictionary['proxy']:
                proxy_info = dictionary['proxy']
                if _is_valid_proxy(proxy_info):
                    print('Setting proxy')
                    proxy = dictionary['proxy']
                else:
                    print('The proxy is not in the right format and it will not be used.')

            debug_log = bool(dictionary.get('debug', False))
            downloads = _normalize_yaml_downloads(dictionary)
            manager = DownloadManager()
            for entry in downloads:
                title = entry.get('title')
                if not title:
                    continue
                request = DownloadRequest(
                    title=title.strip(),
                    source=_normalize_source(entry.get('source', 'fanfox')),
                    output=str(entry.get('output', output)).strip(),
                    pdf=bool(entry.get('pdf', False)),
                    proxy=entry.get('proxy', proxy),
                    enable_debug_log=bool(entry.get('debug', debug_log)),
                    download_all_chapters=bool(entry.get('download_all_chapters', False)),
                    download_last_chapter=bool(entry.get('download_last_chapter', False)),
                    download_single_chapter=entry.get('download_single_chapter'),
                    download_chapters=entry.get('download_chapters'),
                    options=_extract_options(entry),
                )
                manager.download(request)
    except Exception as error:
        print(error)


def main_title(args: argparse.Namespace):
    source = _normalize_source(args.source) if args.source else 'fanfox'
    proxy = None
    if args.proxy:
        if _is_valid_proxy(args.proxy):
            print('Setting proxy')
            proxy = args.proxy
        else:
            print('The proxy is not in the right format and it will not be used.')

    request = DownloadRequest(
        title=args.manga_title.strip(),
        source=source,
        output=args.out.strip(),
        pdf=args.pdf or False,
        proxy=proxy,
        enable_debug_log=args.debug,
        download_all_chapters=bool(args.all),
        download_single_chapter=_parse_single_chapter(args.chapter),
        download_chapters=_parse_chapter_range(args.chapter),
        options=None,
    )
    DownloadManager().download(request)


def _parse_chapter_range(value: str | None) -> str | None:
    if not value:
        return None
    parts = value.split('-')
    if len(parts) == 2:
        return value
    return None


def _parse_single_chapter(value: str | None) -> str | None:
    if not value:
        return None
    parts = value.split('-')
    if len(parts) == 2:
        return None
    return value.strip()


def _is_valid_proxy(proxy_info: dict) -> bool:
    return 'http' in proxy_info.keys() and 'https' in proxy_info.keys()


def _normalize_source(source: str) -> str:
    return source.strip().lower()


def _normalize_yaml_downloads(dictionary: dict) -> list[dict]:
    if 'downloads' in dictionary and isinstance(dictionary['downloads'], list):
        return list(dictionary['downloads'])

    downloads = []
    for key, value in dictionary.items():
        if key in {'debug', 'output', 'proxy'}:
            continue
        if isinstance(value, list):
            for entry in value:
                entry_with_source = dict(entry)
                entry_with_source.setdefault('source', key)
                downloads.append(entry_with_source)
    return downloads


def _extract_options(entry: dict) -> dict | None:
    options = {}
    for key in ("translated_language", "content_rating", "data_saver"):
        if key in entry:
            options[key] = entry.get(key)
    return options or None


if __name__ == '__main__':
    main()
