<INSTRUCTIONS>
## Project summary
`mangapy` is a CLI tool to download manga chapters as images or PDFs. It currently supports a single source: FanFox (fanfox.net).

## Key entrypoints
- CLI: `mangapy/cli.py` (subcommands: `title` and `yaml`)
- Source implementation: `mangapy/fanfox.py`
- Archiving/output: `mangapy/chapter_archiver.py`
- Base models: `mangapy/mangarepository.py`

## How downloads work (high level)
1) `cli.py` parses args / YAML, builds a `MangaDownload`.
2) `FanFoxRepository.search()` finds chapters and returns a `Manga`.
3) `ChapterArchiver.archive()` downloads page images and optionally builds a chapter PDF.

## Behavior and constraints to preserve
- Only `fanfox` is supported today; adding sources should follow the `MangaRepository` pattern.
- Chapter numbers are floats; some chapters are skipped if the number isn't parseable.
- FanFox uses “eval/unpack” JS; do not remove this unless replacing with a working parser.
- `ChapterArchiver` should remain idempotent (skip already-downloaded chapter PDFs or images).

## Testing
- Tests are integration-style and hit live FanFox pages; they are flaky by nature.
- Run with: `pytest -q` (expect failures if FanFox changes or rate-limits).

## Development tips
- Prefer small, localized changes in `fanfox.py` to reduce breakage if the site changes.
- When touching downloads, confirm file paths remain under the output directory and respect `~` expansion.
- Keep CLI defaults stable; this is a published package (`pyproject.toml`, `setup.py`).
</INSTRUCTIONS>
