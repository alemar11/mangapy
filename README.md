# mangapy

Manga downloader supporting the following sources:

- fanfox.net
- mangapark.net

## Installation

```
pip install --upgrade mangapy
```

## Usage

Mangapy let you download manga chapters as images (default) or pdfs.
Use 'mangapy -h' to get a list of all the availabe options.

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

You may need a proxy to download certain manga, to do so use the option *-p or --proxy*:
Downloads the last One Piece chapter as images inside the *Downloads* folder (from Fanfox source) using the proxy during the search.  

```
mangapy "one piece" -o ~/Downloads -p '{"http": "194.226.34.132:8888", "https": "194.226.34.132:8888"}'
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