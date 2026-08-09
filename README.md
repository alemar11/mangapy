# mangapy

Manga downloader supporting the following sources:

- fanfox.net
- mangadex.org (via api.mangadex.org)

## Installation

```
pipx install mangapy
```

Or, on macOS with Homebrew:

```
brew install alemar11/tap/mangapy
```

## Usage

### Terminal

Mangapy lets you download manga chapters as images (default) or PDFs.
Use `mangapy -h` to get a list of all the available options.
Terminal messages are styled automatically when output is interactive and stay
plain when redirected or run in CI. Set `NO_COLOR=1` to disable terminal colors.

Downloads all Bleach chapters as images inside the *Downloads* folder (from FanFox).

```
mangapy title bleach -a -o ~/Downloads
```

Downloads all Bleach chapters as one PDF per chapter inside the *Downloads* folder (from FanFox).

```
mangapy title bleach -a -o ~/Downloads --pdf
```

Downloads Bleach chapter 1 as images inside the *Downloads* folder (from FanFox).

```
mangapy title bleach -c 1 -o ~/Downloads
```

Downloads Bleach chapters from 0 to 10 (included) as images inside the *Downloads* folder using FanFox as source.

```
mangapy title bleach -c 0-10 -o ~/Downloads -s fanfox
```

Disable network retries (useful for benchmarking).

```
mangapy title bleach -c 1 -o ~/Downloads --no-retry
```

Disable progress output.

```
mangapy title bleach -c 1 -o ~/Downloads --no-progress
```

Some providers may require a proxy. Pass a JSON mapping with both `http` and
`https` entries using `-p` or `--proxy`; every proxy URL must include its
scheme. The mapping is used both for provider search/API requests and for
chapter image downloads.

```
mangapy title "one piece" -o ~/Downloads -p '{"http": "http://194.226.34.132:8888", "https": "http://194.226.34.132:8888"}'
```

### Exit codes

- `0`: every requested download completed successfully.
- `1`: an operational, configuration, provider-search, or partial-download error occurred.
- `2`: command-line usage or input was rejected by the argument parser.
- `130`: the process was interrupted by the user.

### YAML

Mangapy lets you download multiple manga chapters as images (default) or PDFs from a *.yaml* file.
For every manga you can choose:

- source (*fanfox*, *mangadex*)
- whether to save each selected chapter as its own PDF
- which chapter to download (single, range, all, last)
- MangaDex-only options: `translated_language`, `content_rating`, `data_saver`

MangaDex output names use the immutable chapter UUID so corrections to chapter
numbers, labels, or languages do not create duplicate downloads and different
translations or scanlations cannot overwrite each other.
Legacy MangaDex outputs that contain only the chapter number are left untouched
and are not reused because they do not identify their translation. In image
mode, each `images/<chapter>` directory is managed by Mangapy and stale regular
files are removed after a complete run.

```
mangapy yaml PATH_TO_YOUR_YAML_FILE
```

Samples for YAML mode live in `samples/`. For local testing from source, run:

```
uv run python3 scripts/dev_run.py <sample-filename.yaml>
```

```yaml
--- 
 debug: true # optional
 no_retry: false # optional, disable retries
 no_progress: false # optional, disable progress output
 output: "~/Downloads/mangapy"
 proxy: # optional
  http: "http://31.14.131.70:8080"
  https: "http://31.14.131.70:8080" 
 downloads:
  - source: "fanfox"
    title: "bleach"
    pdf: true
    download_single_chapter: "10"
    no_retry: true
  - source: "fanfox"
    title: "naruto"
    pdf: true
    download_chapters: "10-13"
  - source: "mangadex"
    title: "blue lock"
    translated_language: ["en"]
    content_rating: ["safe", "suggestive", "erotica"]
    data_saver: false
    download_all_chapters: true
```
