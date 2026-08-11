<div align="center">

# mangapy

**Download manga chapters from the terminal as images or PDFs.**

[![PyPI](https://img.shields.io/pypi/v/mangapy?logo=pypi&logoColor=white)](https://pypi.org/project/mangapy/)
[![Python](https://img.shields.io/pypi/pyversions/mangapy?logo=python&logoColor=white)](https://pypi.org/project/mangapy/)
[![Build](https://github.com/alemar11/mangapy/actions/workflows/pythonpackage.yml/badge.svg)](https://github.com/alemar11/mangapy/actions/workflows/pythonpackage.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

[Getting started](#getting-started) · [CLI examples](#cli-examples) · [YAML mode](#yaml-mode) · [Configuration](#configuration)

</div>

---

`mangapy` is a command-line downloader for [FanFox](https://fanfox.net/) and
[MangaDex](https://mangadex.org/). Download one chapter, a range, the latest
chapter, or an entire series—with one PDF per chapter when you want a portable
archive.

> [!IMPORTANT]
> You need **Python 3.14 or newer** when installing from PyPI. The Homebrew
> formula installs its Python dependency for you.

## Highlights

| | Feature | What it gives you |
| :--: | --- | --- |
| 📚 | Flexible chapter selection | Download one chapter, an inclusive range, the latest chapter, or everything available. |
| 🖼️ | Images or PDFs | Keep the original page images or create a separate PDF for every selected chapter. |
| 🧾 | Batch configuration | Describe downloads from multiple providers in one YAML file. |
| ⚡ | Provider-aware downloads | MangaDex downloads chapters and pages concurrently while respecting its request rate. |
| ♻️ | Safe reruns | Completed chapter images and PDFs are detected so repeat runs do not download them again. |
| 🖥️ | Terminal-friendly output | Interactive terminals get styled progress; redirected output and CI logs stay plain. |

### Supported providers

| Provider | CLI name | Language filtering | Content ratings | Data-saver images |
| --- | :---: | :---: | :---: | :---: |
| [FanFox](https://fanfox.net/) | `fanfox` | — | — | — |
| [MangaDex](https://mangadex.org/) | `mangadex` | ✅ | ✅ | ✅ |

> [!NOTE]
> `fanfox` is the default provider. MangaDex-specific filters are available in
> [YAML mode](#mangadex-options).

## Getting started

### Install with pipx

[`pipx`](https://pipx.pypa.io/) installs `mangapy` in an isolated environment
while making the command available globally:

```console
pipx install mangapy
```

### Install with Homebrew

On macOS:

```console
brew install alemar11/tap/mangapy
```

Confirm the installation:

```console
mangapy --version
mangapy --help
```

## CLI examples

The shortest command downloads the latest available chapter from FanFox as
images into `~/Downloads/mangapy`:

```console
mangapy title bleach
```

### Choose chapters

| Goal | Command |
| --- | --- |
| Download chapter 1 | `mangapy title bleach --chapter 1` |
| Download chapters 0 through 10 | `mangapy title bleach --chapter 0-10` |
| Download every chapter | `mangapy title bleach --all` |
| Use MangaDex | `mangapy title bleach --chapter 1 --source mangadex` |
| Choose an output directory | `mangapy title bleach --chapter 1 --out ~/Downloads` |
| Create one PDF per chapter | `mangapy title bleach --all --pdf` |

Chapter ranges are inclusive. Open-ended ranges are supported too:

```console
# Chapter 85 and every available chapter after it
mangapy title "tower of god" --chapter 85-
```

> [!TIP]
> Quote titles containing spaces. Run `mangapy title --help` for the complete
> command reference.

### Control retries and progress

Disable network retries for benchmarking or fail-fast workflows:

```console
mangapy title bleach --chapter 1 --no-retry
```

Disable the progress display for scripts and compact logs:

```console
mangapy title bleach --chapter 1 --no-progress
```

Set [`NO_COLOR`](https://no-color.org/) to disable terminal colors while
keeping progress output enabled:

```console
NO_COLOR=1 mangapy title bleach --chapter 1
```

### Use a proxy

Pass a JSON object with both `http` and `https` entries. Each URL must include
its scheme; the proxy is used for provider requests and chapter images.

```console
mangapy title "one piece" \
  --out ~/Downloads \
  --proxy '{"http":"http://proxy.example:8080","https":"http://proxy.example:8080"}'
```

> [!CAUTION]
> Treat proxy credentials as secrets. Avoid putting authenticated proxy URLs in
> shell history, shared YAML files, screenshots, or logs.

## YAML mode

YAML mode is useful for repeatable downloads across multiple titles and
providers:

```console
mangapy yaml path/to/downloads.yaml
```

```yaml
---
debug: false
no_retry: false
no_progress: false
output: "~/Downloads/mangapy"

downloads:
  - source: fanfox
    title: bleach
    pdf: true
    download_single_chapter: "10"

  - source: fanfox
    title: naruto
    download_chapters: "10-13"

  - source: mangadex
    title: blue lock
    translated_language: [en]
    content_rating: [safe, suggestive, erotica]
    data_saver: false
    download_all_chapters: true
```

Global settings act as defaults. A download entry can override `debug`,
`no_retry`, `no_progress`, `output`, and `proxy` for that title.

### Chapter selectors

Use at most one selector per download entry:

| YAML field | Example | Selects |
| --- | --- | --- |
| `download_single_chapter` | `"10"` | One chapter |
| `download_chapters` | `"10-13"` | An inclusive range |
| `download_chapters` | `"85-"` | A chapter and everything after it |
| `download_last_chapter` | `true` | The latest downloadable chapter |
| `download_all_chapters` | `true` | Every available chapter |
| _No selector_ | — | The latest downloadable chapter |

### MangaDex options

These fields are valid only when `source: mangadex`:

| YAML field | Default | Description |
| --- | --- | --- |
| `translated_language` | `[en]` | One language code or a list of language codes. |
| `content_rating` | `[safe, suggestive, erotica]` | One rating or a list of ratings accepted by MangaDex. |
| `data_saver` | `false` | Use MangaDex's smaller data-saver page images. |

> [!NOTE]
> MangaDex output names include the immutable chapter UUID. This prevents
> corrected metadata, translations, and scanlations from overwriting one
> another. Legacy number-only outputs are kept but are not reused because they
> do not identify a translation.

<details>
<summary><strong>All YAML fields</strong></summary>

#### Global fields

| Field | Type | Purpose |
| --- | --- | --- |
| `downloads` | list | Download entries to process. |
| `output` | string | Default output directory. |
| `proxy` | mapping | Default `http` and `https` proxy URLs. |
| `debug` | boolean | Enable debug logging. |
| `no_retry` | boolean | Disable network retries. |
| `no_progress` | boolean | Disable progress output. |

#### Per-download fields

| Field | Type | Purpose |
| --- | --- | --- |
| `source` | string | `fanfox` or `mangadex`; defaults to `fanfox`. |
| `title` | string | Manga title to find. Required. |
| `output` | string | Override the global output directory. |
| `pdf` | boolean | Create one PDF for each selected chapter. |
| `proxy` | mapping | Override the global proxy. |
| `debug` | boolean | Override global debug logging. |
| `no_retry` | boolean | Override the global retry setting. |
| `no_progress` | boolean | Override the global progress setting. |
| `download_single_chapter` | string or number | Select one chapter. |
| `download_chapters` | string | Select an inclusive or open-ended range. |
| `download_last_chapter` | boolean | Select the latest downloadable chapter. |
| `download_all_chapters` | boolean | Select every available chapter. |
| `translated_language` | string or list | MangaDex translation language filter. |
| `content_rating` | string or list | MangaDex content-rating filter. |
| `data_saver` | boolean | Use MangaDex data-saver images. |

</details>

More ready-to-run configurations are available in [`samples/`](samples/). To
run one directly from a source checkout:

```console
uv run python3 scripts/dev_run.py sample.yaml
```

## Configuration

### Output layout

Downloads are organized by provider and manga beneath the selected output
directory. Image mode stores page files under an `images` directory; PDF mode
creates one PDF per chapter.

Mangapy owns each completed chapter image directory. After a successful image
download, stale regular files in that chapter directory are removed so the
local pages match the provider response.

### Exit codes

| Code | Meaning |
| :---: | --- |
| `0` | Every requested download completed successfully. |
| `1` | An operational, configuration, search, or partial-download error occurred. |
| `2` | The command line or input was rejected by the argument parser. |
| `130` | The download was interrupted by the user. |

## Development

Clone the repository and use [`uv`](https://docs.astral.sh/uv/) to run the
offline test suite:

```console
git clone https://github.com/alemar11/mangapy.git
cd mangapy
uv sync
uv run pytest -q
```

Live provider tests are excluded by default because they contact third-party
services and may be affected by site changes or rate limits.

## License

Distributed under the [MIT License](LICENSE).
