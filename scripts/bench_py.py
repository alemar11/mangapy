#!/usr/bin/env python3
import argparse
import json
import os
import random
import time
from pathlib import Path

from mangapy.download_manager import _parse_number
from mangapy.chapter_archiver import ChapterArchiver
from mangapy.providers import get_repository


def _pick_chapter(manga, chapter_value):
    if not chapter_value:
        return manga.last_chapter
    number = _parse_number(chapter_value)
    for chapter in manga.chapters:
        if number is not None and chapter.number == number:
            return chapter
        if chapter.chapter_id == chapter_value:
            return chapter
    return manga.last_chapter


def _bench_task(name, rounds, fn):
    runs = []
    for idx in range(rounds):
        start = time.perf_counter()
        fn(idx)
        runs.append((time.perf_counter() - start) * 1000)
    avg = sum(runs) / len(runs) if runs else 0
    return {
        "name": name,
        "runs": runs,
        "avg": avg,
        "min": min(runs) if runs else 0,
        "max": max(runs) if runs else 0,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-s", "--source", default="fanfox")
    parser.add_argument("-t", "--title", default="naruto")
    parser.add_argument("-c", "--chapter")
    parser.add_argument("-o", "--out", default=os.path.join(os.path.expanduser("~"), "Downloads", "mangapy"))
    parser.add_argument("--pdf", action="store_true")
    parser.add_argument("--pdf-only", action="store_true")
    parser.add_argument("--images", action="store_true")
    parser.add_argument("--pages", action="store_true")
    parser.add_argument("-r", "--rounds", type=int, default=1)
    parser.add_argument("--no-retry", action="store_true")
    parser.add_argument("--no-progress", action="store_true")
    parser.add_argument("--translated-language")
    parser.add_argument("--content-rating")
    parser.add_argument("--data-saver", action="store_true")
    args = parser.parse_args()

    options = {}
    if args.translated_language:
        options["translated_language"] = [v.strip() for v in args.translated_language.split(",") if v.strip()]
    if args.content_rating:
        options["content_rating"] = [v.strip() for v in args.content_rating.split(",") if v.strip()]
    if args.data_saver:
        options["data_saver"] = True

    repo = get_repository(args.source)

    results = {}

    def bench_pages():
        manga = repo.search(args.title, options=options)
        if not manga:
            return
        chapter = _pick_chapter(manga, args.chapter)
        chapter.pages()

    def bench_images(pdf=False):
        manga = repo.search(args.title, options=options)
        if not manga:
            return
        chapter = _pick_chapter(manga, args.chapter)
        run_root = os.path.join(args.out, "bench-py", f"{int(time.time()*1000)}-{random.randint(0,99999)}")
        os.makedirs(run_root, exist_ok=True)
        archiver = ChapterArchiver(
            run_root,
            max_workers=repo.capabilities.max_parallel_pages,
            retry_enabled=not args.no_retry,
            show_progress=not args.no_progress,
        )
        archiver.archive(chapter, pdf, repo.image_request_headers())

    def bench_pdf_only():
        manga = repo.search(args.title, options=options)
        if not manga:
            return
        chapter = _pick_chapter(manga, args.chapter)
        run_root = os.path.join(args.out, "bench-py", f"{int(time.time()*1000)}-{random.randint(0,99999)}")
        os.makedirs(run_root, exist_ok=True)
        archiver = ChapterArchiver(
            run_root,
            max_workers=repo.capabilities.max_parallel_pages,
            retry_enabled=not args.no_retry,
            show_progress=not args.no_progress,
        )
        chapter_id = getattr(chapter, "chapter_id", None)
        if chapter.number is not None:
            is_int = isinstance(chapter.number, int) or float(chapter.number).is_integer()
            chapter_name = str(int(chapter.number)) if is_int else str(chapter.number)
        else:
            chapter_name = chapter_id if chapter_id is not None else "unknown"
        # Download images once (not timed)
        archiver._download_chapter_images(chapter, chapter_name, repo.image_request_headers(), pdf=True)
        images_path = Path(run_root).joinpath(".images", chapter_name)

        def _create_pdf(round_idx):
            pdf_dir = Path(run_root).joinpath("pdf")
            pdf_dir.mkdir(parents=True, exist_ok=True)
            pdf_path = pdf_dir.joinpath(f"{chapter_name}-only-{round_idx + 1}.pdf")
            archiver._create_chapter_pdf(images_path, pdf_path)

        return _create_pdf

    if args.pages:
        results["pages"] = _bench_task("search_pages", args.rounds, lambda _idx: bench_pages())
    if args.images:
        results["images"] = _bench_task("download_images", args.rounds, lambda _idx: bench_images(pdf=False))
    if args.pdf:
        results["pdf"] = _bench_task("download_pdf", args.rounds, lambda _idx: bench_images(pdf=True))
    if args.pdf_only:
        creator = bench_pdf_only()
        if creator:
            results["pdf_only"] = _bench_task("pdf_only", args.rounds, creator)

    if not (args.pages or args.images or args.pdf or args.pdf_only):
        results["pages"] = _bench_task("search_pages", args.rounds, lambda _idx: bench_pages())
        results["images"] = _bench_task("download_images", args.rounds, lambda _idx: bench_images(pdf=False))
        results["pdf"] = _bench_task("download_pdf", args.rounds, lambda _idx: bench_images(pdf=True))

    output = {
        "source": args.source,
        "title": args.title,
        "chapter": args.chapter,
        "rounds": args.rounds,
        "results": results,
    }
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
