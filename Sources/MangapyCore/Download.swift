import Darwin
import Foundation

func writeError(_ message: String) {
    FileHandle.standardError.write(Data((message + "\n").utf8))
}

extension DownloadRequest {
    public func run() async throws {
        let http = try HTTP(source: source, retries: retries, proxy: proxy)
        let provider: any Provider
        switch source {
        case .fanfox: provider = FanFox(http: http)
        case .mangadex: provider = MangaDex(http: http, options: mangaDex)
        }
        try await run(provider: provider, http: http)
    }

    func run(provider: any Provider, http: HTTP) async throws {
        if showProgress { writeError("Searching for \(title)") }
        let manga = try await provider.search(title)
        let chapters = selection.select(manga.chapters.sorted(by: Chapter.precedes))
        guard !chapters.isEmpty else { throw MangapyError("No matching chapters found for \(manga.title)") }
        var names = Set<String>()
        var jobs: [(Chapter, String)] = []
        for chapter in chapters {
            let name = chapterName(chapter, source: source)
            if names.insert(name.lowercased()).inserted {
                jobs.append((chapter, name))
            } else if source == .mangadex {
                throw MangapyError("Chapter output names collide: \(name)")
            }
        }

        let root = try mangaDirectory(at: output, source: source, title: manga.title)
        let archiver = Archiver(root: root, http: http, provider: provider, pageWorkers: source.pageWorkers, pdf: pdf, force: force)
        try await withMangaLock(at: root) {
            try await download(jobs, for: manga.title, archiver: archiver)
        }
    }

    private func download(_ jobs: [(Chapter, String)], for title: String, archiver: Archiver) async throws {
        let terminal = showProgress && isatty(STDERR_FILENO) == 1
        let colored = terminal && ProcessInfo.processInfo.environment["NO_COLOR"] == nil
        var downloaded = 0
        var existing = 0
        var failed = 0
        for start in stride(from: 0, to: jobs.count, by: source.chapterWorkers) {
            try Task.checkCancellation()
            let batch = jobs[start..<min(start + source.chapterWorkers, jobs.count)]
            if showProgress && !terminal {
                for (chapter, _) in batch { writeError("\(title) · chapter \(chapter.label)") }
            }
            let results = await batchResults(batch) { try await archiver.archive($0.0, name: $0.1) }
            for ((_, name), result) in zip(batch, results) {
                switch result {
                case .success(.downloaded): downloaded += 1
                case .success(.existing): existing += 1
                case .success(.unavailable):
                    writeError("Chapter \(name) unavailable")
                    failed += 1
                case .failure(let error):
                    let description = debug ? String(reflecting: error) : error.localizedDescription
                    writeError("Chapter \(name): \(description)")
                    failed += 1
                }
            }
            if terminal {
                let message = "\(title) · \(downloaded + existing + failed)/\(jobs.count) chapters"
                writeError(colored ? "\u{001B}[36m\(message)\u{001B}[0m" : message)
            }
        }
        try Task.checkCancellation()
        print("\(title) · \(downloaded) downloaded, \(existing) already present, \(failed) incomplete")
        if failed > 0 { throw MangapyError("\(failed) chapter(s) incomplete") }
    }
}
