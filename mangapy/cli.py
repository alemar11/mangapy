import argparse
import importlib.metadata
import json
import os
import sys
from collections.abc import Mapping
from pathlib import Path
from urllib.parse import urlparse

import yaml

from mangapy import terminal
from mangapy.download_manager import DownloadManager, DownloadRequest
from mangapy.providers import available_providers

try:
    version = importlib.metadata.version("mangapy")
except importlib.metadata.PackageNotFoundError:
    version = "0.0.0"
default_path_to_download_folder = str(os.path.join(Path.home(), "Downloads", "mangapy"))

_GLOBAL_YAML_KEYS = {"debug", "downloads", "force", "no_progress", "no_retry", "output", "proxy"}
_DOWNLOAD_YAML_KEYS = {
    "content_rating",
    "data_saver",
    "debug",
    "download_all_chapters",
    "download_chapters",
    "download_last_chapter",
    "download_single_chapter",
    "force",
    "no_progress",
    "no_retry",
    "output",
    "pdf",
    "proxy",
    "source",
    "title",
    "translated_language",
}
_MANGADEX_OPTION_KEYS = {"content_rating", "data_saver", "translated_language"}


def cmd_parse():
    """Returns parsed arguments from command line"""
    parser = argparse.ArgumentParser()

    subparsers = parser.add_subparsers(help="Download modes.", dest="mode", required=True)

    yaml_parser = subparsers.add_parser("yaml")
    args_parser = subparsers.add_parser("title")

    yaml_parser.add_argument("yaml_file", type=str, help="Path to the .yaml file")

    args_parser.add_argument("manga_title", type=str, help="manga title to download")
    args_parser.add_argument("-s", "--source", type=str.lower, choices=available_providers(), help="manga source")
    args_parser.add_argument("-o", "--out", type=str, default=default_path_to_download_folder, help="download directory")
    args_parser.add_argument("-d", "--debug", action="store_true", help="set log to DEBUG level")
    args_parser.add_argument("--pdf", action="store_true", help="create a pdf for each chapter")
    args_parser.add_argument("--force", action="store_true", help="redownload and replace existing chapter files")
    args_parser.add_argument("--no-retry", action="store_true", help="disable network retries")
    args_parser.add_argument("--no-progress", action="store_true", help="disable progress output")

    args_parser.add_argument("-p", "--proxy", type=json.loads, help="use a proxy to download the chapters")
    group = args_parser.add_mutually_exclusive_group()
    group.add_argument("-a", "--all", action="store_true", help="download all chapters available")
    group.add_argument("-c", "--chapter", type=str, help="chapter(s) number to download")

    parser.add_argument(
        "-v", "--version", action="version", version="{0} {1}".format(parser.prog, version), help="show program version and exit"
    )

    args = parser.parse_args(sys.argv[1:])
    return args


def main() -> int:
    try:
        args = cmd_parse()
        if args.mode == "title":
            return main_title(args)
        return main_yaml(args)
    except KeyboardInterrupt:
        terminal.warning("Download canceled by user.", icon="■", to_stderr=False)
        return 130


def main_yaml(args: argparse.Namespace) -> int:
    yaml_file = args.yaml_file.strip()

    try:
        with open(yaml_file, encoding="utf-8") as file:
            dictionary = yaml.safe_load(file)
    except (OSError, yaml.YAMLError) as error:
        terminal.error(f"Unable to read YAML configuration: {error}")
        return 1

    if not isinstance(dictionary, Mapping):
        terminal.error("YAML configuration must contain a mapping at the document root.")
        return 1

    try:
        output = _text_value(dictionary.get("output", default_path_to_download_folder), "output")
        proxy = _proxy_value(dictionary.get("proxy"), "proxy")
        debug_log = _bool_value(dictionary, "debug", False)
        force = _bool_value(dictionary, "force", False)
        no_retry = _bool_value(dictionary, "no_retry", False)
        no_progress = _bool_value(dictionary, "no_progress", False)
        downloads = _normalize_yaml_downloads(dictionary)
    except ValueError as error:
        terminal.error(f"Invalid YAML configuration: {error}")
        return 1

    if not downloads:
        terminal.error("YAML configuration does not contain any downloads.")
        return 1

    manager = DownloadManager()
    failures = 0
    for index, entry in enumerate(downloads, start=1):
        try:
            request = _download_request_from_yaml(
                entry,
                default_output=output,
                default_proxy=proxy,
                default_debug=debug_log,
                default_force=force,
                default_no_retry=no_retry,
                default_no_progress=no_progress,
            )
        except ValueError as error:
            terminal.error(f"Invalid download entry {index}: {error}")
            failures += 1
            continue

        try:
            result = manager.download(request)
        except Exception as error:
            terminal.error(f"Download entry {index} failed unexpectedly: {error}")
            failures += 1
            continue
        if not result.succeeded:
            failures += 1

    return 0 if failures == 0 else 1


def main_title(args: argparse.Namespace) -> int:
    source = _normalize_source(args.source) if args.source else "fanfox"
    if source not in available_providers():
        terminal.error(f"Unknown manga source: {source}")
        return 1
    try:
        title = _text_value(args.manga_title, "manga title")
        output = _text_value(args.out, "output")
    except ValueError as error:
        terminal.error(error)
        return 1
    proxy = None
    if args.proxy is not None:
        if _is_valid_proxy(args.proxy):
            terminal.info("Using configured proxy.", icon="↗")
            proxy = dict(args.proxy)
        else:
            terminal.error("The proxy must define valid http:// or https:// URLs for both http and https.")
            return 1

    request = DownloadRequest(
        title=title,
        source=source,
        output=output,
        pdf=bool(args.pdf),
        force=bool(getattr(args, "force", False)),
        proxy=proxy,
        no_retry=bool(getattr(args, "no_retry", False)),
        no_progress=bool(getattr(args, "no_progress", False)),
        enable_debug_log=args.debug,
        download_all_chapters=bool(args.all),
        download_single_chapter=_parse_single_chapter(args.chapter),
        download_chapters=_parse_chapter_range(args.chapter),
        options=None,
    )
    try:
        result = DownloadManager().download(request)
    except Exception as error:
        terminal.error(f"Download failed unexpectedly: {error}")
        return 1
    return 0 if result.succeeded else 1


def _parse_chapter_range(value: str | None) -> str | None:
    if not value:
        return None
    parts = value.split("-")
    if len(parts) == 2:
        return value
    return None


def _parse_single_chapter(value: str | None) -> str | None:
    if not value:
        return None
    parts = value.split("-")
    if len(parts) == 2:
        return None
    return value.strip()


def _is_valid_proxy(proxy_info: object) -> bool:
    if not isinstance(proxy_info, Mapping):
        return False
    for scheme in ("http", "https"):
        value = proxy_info.get(scheme)
        if not isinstance(value, str):
            return False
        try:
            parsed = urlparse(value)
            hostname = parsed.hostname
            parsed.port
        except ValueError:
            return False
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or not hostname
            or any(character.isspace() for character in hostname)
        ):
            return False
    return True


def _normalize_source(source: str) -> str:
    return source.strip().lower()


def _normalize_yaml_downloads(dictionary: Mapping) -> list[Mapping]:
    providers = {name.casefold(): name for name in available_providers()}
    provider_groups: dict[object, str] = {}
    unknown = []
    for key in dictionary:
        if key in _GLOBAL_YAML_KEYS:
            continue
        if isinstance(key, str) and key.casefold() in providers:
            canonical_name = providers[key.casefold()]
            if canonical_name in provider_groups.values():
                raise ValueError(f"duplicate legacy provider group for {canonical_name}")
            provider_groups[key] = canonical_name
        else:
            unknown.append(key)
    if unknown:
        rendered = ", ".join(sorted((repr(key) for key in unknown)))
        raise ValueError(f"YAML root contains unknown field(s): {rendered}")

    if "downloads" in dictionary:
        if provider_groups:
            raise ValueError("downloads cannot be combined with legacy provider groups")
        if not isinstance(dictionary["downloads"], list):
            raise ValueError("downloads must be a list")
        downloads = list(dictionary["downloads"])
        if not all(isinstance(entry, Mapping) for entry in downloads):
            raise ValueError("every downloads item must be a mapping")
        return downloads

    downloads = []
    for key, value in dictionary.items():
        if key in _GLOBAL_YAML_KEYS:
            continue
        if not isinstance(value, list):
            raise ValueError(f"{key} must be a list")
        for entry in value:
            if not isinstance(entry, Mapping):
                raise ValueError(f"every {key} item must be a mapping")
            entry_with_source = dict(entry)
            entry_with_source.setdefault("source", provider_groups[key])
            downloads.append(entry_with_source)
    return downloads


def _extract_options(entry: Mapping) -> dict | None:
    options = {}
    for key in ("translated_language", "content_rating"):
        if key in entry:
            options[key] = _string_list_value(entry.get(key), key)
    if "data_saver" in entry:
        options["data_saver"] = _bool_value(entry, "data_saver", False)
    return options or None


def _download_request_from_yaml(
    entry: Mapping,
    *,
    default_output: str,
    default_proxy: dict | None,
    default_debug: bool,
    default_force: bool,
    default_no_retry: bool,
    default_no_progress: bool,
) -> DownloadRequest:
    _validate_mapping_keys(entry, _DOWNLOAD_YAML_KEYS, "download entry")
    title = _text_value(entry.get("title"), "title")
    source = _normalize_source(_text_value(entry.get("source", "fanfox"), "source"))
    if source not in available_providers():
        raise ValueError(f"unknown source {source!r}; choose one of: {', '.join(available_providers())}")
    if source != "mangadex" and _MANGADEX_OPTION_KEYS.intersection(entry):
        raise ValueError("translated_language, content_rating, and data_saver are supported only by MangaDex")
    output = _text_value(entry.get("output", default_output), "output")
    proxy = _proxy_value(entry.get("proxy", default_proxy), "proxy")

    download_all = _bool_value(entry, "download_all_chapters", False)
    download_last = _bool_value(entry, "download_last_chapter", False)
    single = _optional_chapter_value(entry.get("download_single_chapter"), "download_single_chapter")
    chapter_range = _optional_chapter_value(entry.get("download_chapters"), "download_chapters")
    selectors = [download_all, download_last, single is not None, chapter_range is not None]
    if sum(selectors) > 1:
        raise ValueError("chapter selection fields are mutually exclusive")

    return DownloadRequest(
        title=title,
        source=source,
        output=output,
        pdf=_bool_value(entry, "pdf", False),
        force=_bool_value(entry, "force", default_force),
        proxy=proxy,
        no_retry=_bool_value(entry, "no_retry", default_no_retry),
        no_progress=_bool_value(entry, "no_progress", default_no_progress),
        enable_debug_log=_bool_value(entry, "debug", default_debug),
        download_all_chapters=download_all,
        download_last_chapter=download_last,
        download_single_chapter=single,
        download_chapters=chapter_range,
        options=_extract_options(entry),
    )


def _text_value(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


def _optional_chapter_value(value: object, name: str) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise ValueError(f"{name} must be a chapter number or range string")
    normalized = str(value).strip()
    if not normalized:
        raise ValueError(f"{name} cannot be empty")
    return normalized


def _bool_value(mapping: Mapping, name: str, default: bool) -> bool:
    if name not in mapping:
        return default
    value = mapping[name]
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be true or false")
    return value


def _proxy_value(value: object, name: str) -> dict | None:
    if value is None:
        return None
    if not _is_valid_proxy(value):
        raise ValueError(f"{name} must define http and https proxy URLs including their scheme")
    return dict(value)


def _string_list_value(value: object, name: str) -> list[str]:
    values = [value] if isinstance(value, str) else value
    if not isinstance(values, list) or not values or not all(isinstance(item, str) and item.strip() for item in values):
        raise ValueError(f"{name} must be a non-empty string or list of non-empty strings")
    return [item.strip() for item in values]


def _validate_mapping_keys(mapping: Mapping, allowed: set[str], context: str) -> None:
    unknown = [key for key in mapping if not isinstance(key, str) or key not in allowed]
    if unknown:
        rendered = ", ".join(sorted((repr(key) for key in unknown)))
        raise ValueError(f"{context} contains unknown field(s): {rendered}")


if __name__ == "__main__":
    raise SystemExit(main())
