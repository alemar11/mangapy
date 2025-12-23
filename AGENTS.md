<INSTRUCTIONS>
## Project summary
`mangapy` is a CLI tool to download manga chapters as images or PDFs from multiple providers. Current providers: FanFox (fanfox.net) and MangaDex (api.mangadex.org).

## Key entrypoints
- CLI: `mangapy/cli.py` (subcommands: `title` and `yaml`)
- Provider registry + selection: `mangapy/providers.py`, `mangapy/download_manager.py`
- Provider implementations: `mangapy/fanfox.py`, `mangapy/mangadex.py`
- Archiving/output: `mangapy/chapter_archiver.py`
- Base models: `mangapy/mangarepository.py`

## How downloads work (high level)
1) `cli.py` parses args / YAML, builds a `MangaDownload`.
2) Provider repository `search()` finds chapters and returns a `Manga`.
3) `ChapterArchiver.archive()` downloads page images and optionally builds a chapter PDF.

## Behavior and constraints to preserve
- Providers are registered via `mangapy/providers.py`; add new sources there and expose capabilities.
- Chapter numbers are floats; some chapters are skipped if the number isn't parseable.
- FanFox uses “eval/unpack” JS; do not remove this unless replacing with a working parser.
- `ChapterArchiver` should remain idempotent (skip already-downloaded chapter PDFs or images).

## Testing
- Live tests hit real providers and can be flaky (site changes, rate limits).
- Provider-parity rule: for any new provider, add the same baseline live tests with the exact names `test_fetch_manga` and `test_fetch_manga_chapter_pages` (same names across providers). Provider-specific tests should be prefixed with the provider name.
- Run with: `pytest -q`.

## Development tips
- Prefer small, localized changes in `fanfox.py` to reduce breakage if the site changes.
- When touching downloads, confirm file paths remain under the output directory and respect `~` expansion.
- Keep CLI defaults stable; this is a published package (`pyproject.toml`).

## Samples
- Sample YAML files live in `samples/`.
- To run a sample locally, use the dev helper: `python3 scripts/dev_run.py <sample-filename.yaml>`.
- If running from source, prefer `uv run python3 scripts/dev_run.py <sample-filename.yaml>` so dependencies are available.
</INSTRUCTIONS>
