import Foundation

struct MangaDex: Provider {
    static let baseURL = URL(string: "https://api.mangadex.org")!
    let http: HTTP
    var base = Self.baseURL
    var options = MangaDexOptions()
    var pacer = RequestPacer()

    private struct Response<Item: Decodable>: Decodable {
        let data: [Item]
        let total: Int?
    }

    private struct Record<Attributes: Decodable>: Decodable {
        let id: String
        let attributes: Attributes
    }

    private struct TitleInfo: Decodable {
        let title: [String: String]?
        let altTitles: [[String: String]]?

        var display: String? {
            title?["en"] ?? title?.sorted { $0.key < $1.key }.first?.value
        }

        var names: [String] {
            ([title ?? [:]] + (altTitles ?? [])).flatMap { $0.values }
        }
    }

    private struct ChapterInfo: Decodable {
        let chapter: String?
        let volume: String?
        let pages: Int?
        let externalUrl: String?
    }

    private struct PageResponse: Decodable {
        struct Pages: Decodable {
            let hash: String
            let data: [String]?
            let dataSaver: [String]?
        }

        let result: String
        let baseUrl: String?
        let chapter: Pages?
    }

    private func json<T: Decodable>(_ url: URL) async throws -> T {
        let bytes = try await http.get(url, pacer: pacer)
        return try JSONDecoder().decode(T.self, from: bytes)
    }

    func search(_ title: String) async throws -> Manga {
        let query = [URLQueryItem(name: "limit", value: "10"), .init(name: "title", value: title)]
        let response: Response<Record<TitleInfo>> = try await json(endpoint("/manga", at: base, query: query))
        let normalized = title.normalizedTitle
        var partial: Record<TitleInfo>?
        var exact: Record<TitleInfo>?
        for record in response.data {
            let names = record.attributes.names.map(\.normalizedTitle)
            if names.contains(normalized) {
                exact = record
                break
            }
            if partial == nil, !normalized.isEmpty, names.contains(where: { $0.contains(normalized) }) {
                partial = record
            }
        }
        guard let match = exact ?? partial else {
            throw notFound(title, suggestions: response.data.prefix(5).compactMap { $0.attributes.display })
        }
        let display = match.attributes.display ?? title
        let chapters = try await feed(id: match.id)
        guard !chapters.isEmpty else {
            throw MangapyError("\(display) found, but no chapters matched languages (\(options.languages.joined(separator: ", "))) and content ratings (\(options.ratings.joined(separator: ", ")))")
        }
        return Manga(title: display, chapters: chapters)
    }

    private func feed(id: String) async throws -> [Chapter] {
        let filters = options.languages.map { URLQueryItem(name: "translatedLanguage[]", value: $0) }
            + options.ratings.map { URLQueryItem(name: "contentRating[]", value: $0) }
        let server = try endpoint("/at-home/server/", at: base)
        var chapters: [Chapter] = []
        var seen = Set<String>()
        var total = 0
        repeat {
            let query = [
                URLQueryItem(name: "manga", value: id),
                .init(name: "limit", value: "100"),
                .init(name: "offset", value: String(chapters.count)),
                .init(name: "order[chapter]", value: "asc"),
            ] + filters
            let response: Response<Record<ChapterInfo>> = try await json(endpoint("/chapter", at: base, query: query))
            guard let reported = response.total, reported >= 0 else {
                throw MangapyError("Missing MangaDex chapter total")
            }
            total = max(total, reported, chapters.count + response.data.count)
            if response.data.isEmpty, chapters.count < total {
                throw MangapyError("MangaDex feed ended before its declared total")
            }
            for entry in response.data {
                let attrs = entry.attributes
                guard !entry.id.isEmpty else { throw MangapyError("Missing chapter ID") }
                guard seen.insert(entry.id.lowercased()).inserted else {
                    throw MangapyError("Duplicate MangaDex chapter ID \(entry.id)")
                }
                chapters.append(Chapter(
                    id: entry.id,
                    label: (attrs.chapter?.isEmpty == false ? attrs.chapter : nil) ?? entry.id,
                    number: attrs.chapter.flatMap(decimal),
                    volume: attrs.volume.flatMap(decimal),
                    url: try appendingSegments([entry.id], to: server),
                    count: attrs.pages.flatMap { $0 >= 0 ? $0 : nil },
                    external: attrs.externalUrl?.isEmpty == false
                ))
            }
        } while chapters.count < total
        return chapters
    }

    func pages(_ chapter: Chapter) async throws -> [URL] {
        let response: PageResponse = try await json(chapter.url)
        guard response.result == "ok" else { throw MangapyError("MangaDex rejected chapter page request") }
        guard let server = response.baseUrl else { throw MangapyError("Missing image server") }
        guard let chapter = response.chapter else { throw MangapyError("Missing image hash") }
        guard let files = options.dataSaver ? chapter.dataSaver : chapter.data else {
            throw MangapyError("Missing image list")
        }
        let base = try appendingSegments([options.dataSaver ? "data-saver" : "data", chapter.hash], to: remoteURL(server))
        return try files.map { try appendingSegments([$0], to: base) }
    }
}
