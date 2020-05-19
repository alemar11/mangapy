# mangapy

Manga downloader supporting the following sources:

- fanfox.net
- mangapark.net

## Installation

```
pip install --upgrade mangapy
```

## Usage

### Terminal

Mangapy let you download manga chapters as images (default) or pdfs.
Use 'mangapy -h' to get a list of all the availabe options.

Downloads all Bleach chatpers as images inside the *Downloads* folder (from Fanfox source).  

```
mangapy title bleach -a -o ~/Downloads
```

Downloads all Bleach chatpers as a single **.pdf** file inside the *Downloads* folder (from Fanfox source).  

```
mangapy title bleach -a -o ~/Downloads --pdf
```

Downloads Bleach chatper 1 as images inside the *Downloads* folder (from Fanfox source).  

```
mangapy title bleach -c 1 -o ~/Downloads
```

Downloads Bleach chatpers from 0 to 10 (included) as images inside the *Downloads* folder using MangaPark as source.  

```
mangapy title bleach -c 0-10 -o ~/Downloads -s mangapark
```

You may need a proxy to download certain manga, to do so use the option *-p or --proxy*:
Downloads the last One Piece chapter as images inside the *Downloads* folder (from Fanfox source) using the proxy during the search.  

```
mangapy title "one piece" -o ~/Downloads -p '{"http": "194.226.34.132:8888", "https": "194.226.34.132:8888"}'
```

### YAML

Mangapy let you download multiple manga chapters as images (default) or pdfs from a *.yaml* file.
For every manga you can choose:
- source (*fanfox* or *mangapark*)
- whether or not save the manga as a single pdf
- which chapter to download (single, range, all, last)

```
mangapy yaml PATH_TO_YOUR_YAML_FILE
```

```yaml
--- 
 debug: true # optional
 output: "~/Downloads/mangapy"
 proxy: # optional
  http: "http://31.14.131.70:8080"
  https: "http://31.14.131.70:8080" 
 fanfox:
  - title: "bleach"
    pdf: true
    download_single_chapter: "10"
  - title: "naruto"
    pdf: true
    download_chapters: "10-13"
  - title: "black clover"
    download_all_chapters: True
    pdf: true
 mangapark:
  - title: "black clover tabata yuuki"
    pdf: true
    download_last_chapter: True
  - title: "Daiya no A"
    pdf: true
    download_chapters: "111-"
```