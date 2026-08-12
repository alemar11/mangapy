

# mangapy

Descargador de manga que admite las siguientes fuentes:

- fanfox.net
- mangadex.org (vía api.mangadex.org)

## Instalación

```
pipx install mangapy
```

O, en macOS con Homebrew:

```
brew install alemar11/tap/mangapy
```

## Uso

### Terminal

Mangapy te permite descargar capítulos de manga como imágenes (por defecto) o PDFs.
Usa 'mangapy -h' para obtener una lista de todas las opciones disponibles.

Descarga todos los capítulos de Bleach como imágenes dentro de la carpeta *Downloads* (desde la fuente Fanfox).  

```
mangapy title bleach -a -o ~/Downloads
```

Descarga todos los capítulos de Bleach como un único archivo **.pdf** dentro de la carpeta *Downloads* (desde la fuente Fanfox).  

```
mangapy title bleach -a -o ~/Downloads --pdf
```

Descarga el capítulo 1 de Bleach como imágenes dentro de la carpeta *Downloads* (desde la fuente Fanfox).  

```
mangapy title bleach -c 1 -o ~/Downloads
```

Descarga los capítulos de Bleach del 0 al 10 (incluido) como imágenes dentro de la carpeta *Downloads* utilizando Fanfox como fuente.  

```
mangapy title bleach -c 0-10 -o ~/Downloads -s fanfox
```

Desactivar reintentos de red (útil para pruebas de rendimiento).

```
mangapy title bleach -c 1 -o ~/Downloads --no-retry
```

Desactivar la salida de progreso.

```
mangapy title bleach -c 1 -o ~/Downloads --no-progress
```

Es posible que necesites un proxy para descargar ciertos mangas, para hacerlo usa la opción *-p o --proxy*:
Descarga el último capítulo de One Piece como imágenes dentro de la carpeta *Downloads* (desde la fuente Fanfox) utilizando el proxy durante la búsqueda.  

```
mangapy title "one piece" -o ~/Downloads -p '{"http": "194.226.34.132:8888", "https": "194.226.34.132:8888"}'
```

### YAML

Mangapy te permite descargar múltiples capítulos de manga como imágenes (por defecto) o PDFs desde un archivo *.yaml*.
Para cada manga puedes elegir:
- fuente (*fanfox*, *mangadex*)
- si guardar o no el manga como un único PDF
- qué capítulo descargar (único, rango, todos, último)
- Opciones exclusivas de MangaDex: `translated_language`, `content_rating`, `data_saver`

```
mangapy yaml PATH_TO_YOUR_YAML_FILE
```

Las muestras para el modo YAML se encuentran en `samples/`. Para pruebas locales desde el código fuente, ejecuta:

```
uv run python3 scripts/dev_run.py <sample-filename.yaml>
```

```yaml
--- 
 debug: true # opcional
 no_retry: false # opcional, desactiva reintentos
 no_progress: false # opcional, desactiva la salida de progreso
 output: "~/Downloads/mangapy"
 proxy: # opcional
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
