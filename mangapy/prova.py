from mangapark import MangaParkRepository

if __name__ == "__main__":
    repository = MangaParkRepository()
    manga = repository.search("naruto")
    if manga is not None:
        print(len(manga.chapters))
        firstChapter = manga.chapters[0]
        pages = firstChapter.pages()
        for page in pages:
            print(page.number)
