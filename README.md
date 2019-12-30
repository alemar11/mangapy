# mangapy

Manga downloader supporting the following sources:

- fanfox.net
- mangapark.net

## Installation

```
pip install --upgrade mangapy
```

## Usage

Mangapy let you download manga chapters as images or pdfs:

Downloads all Bleach chatpers as images inside the *Downloads* folder (from Fanfox source).
```
mangapy bleach -a -o ~/Downloads
```

Downloads all Bleach chatpers as a single **.pdf** file inside the *Downloads* folder (from Fanfox source).
```
mangapy bleach -a -o ~/Downloads --pdf
```

Downloads Bleach chatper 1 as images inside the *Downloads* folder (from Fanfox source).
```
mangapy bleach -c 1 -o ~/Downloads
```

Downloads Bleach chatpers from 0 to 10 (included) as images inside the *Downloads* folder using MangaPark as source.
```
mangapy bleach -c 0-10 -o ~/Downloads -s mangapark
```

## Development

Install from local folder

```
pip install .
```

Install from local folder (editable mode)

```
pip install -e .
```

Install a local setup.py into your virtual environment/Pipfile:

```
pipenv install -e .
```

Run tests:

```
pipenv run pytest
```