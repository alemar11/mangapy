import Foundation
import os
import Testing
@testable import MangapyCore

private struct FixtureRoutes: Sendable {
    typealias Handler = @Sendable (URLRequest, Int) -> (Int, [String: String], Data)

    private struct State: Sendable {
        var routes: [String: Handler] = [:]
        var counts: [String: Int] = [:]
    }

    private let lock = OSAllocatedUnfairLock(initialState: State())

    func register(_ host: String, handler: @escaping Handler) {
        lock.withLock { $0.routes[host] = handler }
    }

    func count(_ host: String, path: String) -> Int {
        lock.withLock { $0.counts[host + path, default: 0] }
    }

    func respond(_ request: URLRequest) -> (Int, [String: String], Data) {
        let host = request.url!.host!
        let key = host + request.url!.path
        let (route, count) = lock.withLock { state in
            let count = state.counts[key, default: 0] + 1
            state.counts[key] = count
            return (state.routes[host], count)
        }
        return route?(request, count) ?? (404, [:], Data())
    }
}

private final class FixtureProtocol: URLProtocol {
    static let routes = FixtureRoutes()
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        let (status, headers, data) = Self.routes.respond(request)
        let response = HTTPURLResponse(url: request.url!, statusCode: status, httpVersion: "HTTP/1.1", headerFields: headers)!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: data)
        client?.urlProtocolDidFinishLoading(self)
    }

    override func stopLoading() {}
}

private func reply(_ text: String, status: Int = 200, headers: [String: String] = [:]) -> (Int, [String: String], Data) {
    (status, headers, Data(text.utf8))
}

@Test func noRetryMakesExactlyOneNetworkAttempt() async throws {
    let host = "no-retry-fixture.test"
    FixtureProtocol.routes.register(host) { _, _ in reply("", status: 503, headers: ["Retry-After": "0"]) }
    let http = try HTTP(source: .fanfox, retries: false, protocolClasses: [FixtureProtocol.self])
    await #expect(throws: HTTPError.self) { try await http.get(URL(string: "https://\(host)/unavailable")!) }
    #expect(FixtureProtocol.routes.count(host, path: "/unavailable") == 1)
}

@Test func mangadexSearchPaginationHTTPSegmentsAndRetry() async throws {
    let host = "mangadex-fixture.test"
    FixtureProtocol.routes.register(host) { request, count in
        let url = request.url!
        let query = URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems ?? []
        switch url.path {
        case "/manga":
            guard query.contains(.init(name: "title", value: "Alternate + Title")) else { return reply("", status: 400) }
            if count == 1 { return reply("", status: 429, headers: ["Retry-After": "0"]) }
            return reply(#"{"data":[{"id":"partial","attributes":{"title":{"en":"Alternate + Title 2"}}},{"id":"exact","attributes":{"title":{"en":"Primary"},"altTitles":[{"ja":"Alternate + Title"}]}}]}"#)
        case "/chapter":
            guard query.contains(.init(name: "manga", value: "exact")),
                  query.contains(.init(name: "translatedLanguage[]", value: "ja")) else { return reply("", status: 400) }
            if query.contains(.init(name: "offset", value: "0")) {
                return reply(#"{"total":2,"data":[{"id":"one","attributes":{"chapter":"10.5","pages":2}}]}"#)
            }
            return reply(#"{"total":2,"data":[{"id":"two","attributes":{"chapter":"Special","pages":0,"externalUrl":"https://example.org/"}}]}"#)
        case "/at-home/server/one":
            return reply(#"{"result":"ok","baseUrl":"https://fixture.test/prefix/","chapter":{"hash":"hash","dataSaver":["b c.jpg","a#x.jpg"]}}"#)
        default: return reply("", status: 404)
        }
    }
    let http = try HTTP(source: .mangadex, retries: true, protocolClasses: [FixtureProtocol.self])
    let provider = MangaDex(http: http, base: URL(string: "https://\(host)")!,
                            options: MangaDexOptions(languages: ["ja"], dataSaver: true))
    let manga = try await provider.search("Alternate + Title")
    #expect(manga.title == "Primary")
    #expect(manga.chapters.map(\.label) == ["10.5", "Special"])
    #expect(!manga.chapters[1].downloadable)
    let files = try await provider.pages(manga.chapters[0])
    #expect(files.map(\.absoluteString) == [
        "https://fixture.test/prefix/data-saver/hash/b%20c.jpg",
        "https://fixture.test/prefix/data-saver/hash/a%23x.jpg",
    ])
    #expect(FixtureProtocol.routes.count(host, path: "/manga") == 2)
}

@Test func fanfoxSearchFallbackAndPackedChapterBatches() async throws {
    let host = "fanfox-fixture.test"
    FixtureProtocol.routes.register(host) { request, _ in
        guard request.value(forHTTPHeaderField: "Cookie") == "isAdult=1" else { return reply("", status: 403) }
        let url = request.url!
        switch url.path {
        case "/search":
            return reply(#"<ul class="manga-list-4-list"><li><p class="manga-list-4-item-title"><a href="/manga/translated/">Lookup</a></p></li></ul>"#)
        case "/manga/translated":
            return reply(#"<div id="list-1"><ul class="detail-main-list"><li><a href="/manga/translated/c001/1.html">1</a></li></ul></div><div id="list-2"><ul class="detail-main-list"><li><a href="/manga/translated/c001/1.html">duplicate</a><a href="/manga/translated/c010.5/1.html">10.5</a></li></ul></div>"#)
        case "/manga/translated/c001/1.html":
            return reply(#"<script>chapterid = 123; imagecount = 3; eval(function(p,a,c,k,e,d){}("var guidkey='secret';",62,0,''.split('|')))</script>"#)
        case "/manga/translated/c001/chapterfun.ashx":
            switch url.query {
            case "cid=123&page=1&key=secret":
                return reply(#"eval(function(p,a,c,k,e,d){}('pix="https://images.example"; images=["/01.jpg","/02.jpg"];',62,0,''.split('|')))"#)
            case "cid=123&page=3&key=secret":
                return reply(#"eval(function(p,a,c,k,e,d){}('pix="https://images.example"; images=["/03.jpg"];',62,0,''.split('|')))"#)
            default: return reply("", status: 403)
            }
        case "/manga/translated/c010.5/1.html":
            return reply(#"<script>eval(function(p,a,c,k,e,d){}('newImgs=["https://images.example/inline.png"];',62,0,''.split('|')))</script>"#)
        default: return reply("", status: 404)
        }
    }
    let http = try HTTP(source: .fanfox, retries: false, protocolClasses: [FixtureProtocol.self])
    let provider = FanFox(http: http, base: URL(string: "https://\(host)")!)
    let manga = try await provider.search("Lookup")
    #expect(manga.chapters.compactMap(\.number) == [1, 10.5])
    let files = try await provider.pages(manga.chapters[0])
    #expect(files.map(\.lastPathComponent) == ["01.jpg", "02.jpg", "03.jpg"])
    #expect(provider.headers(for: files[0])["Cookie"] == nil)
    #expect(try await provider.pages(manga.chapters[1]).map(\.lastPathComponent) == ["inline.png"])
    #expect(try PackedScript.unpack(#"eval(function(p,a,c,k,e,d){}('0="1";',62,2,'pix|https://example.org'.split('|')))"#)
        == #"pix="https://example.org";"#)
    #expect(try PackedScript.unpack(#"eval(function(p,a,c,k,e,d){}('0=1;',62,2,'pix|'.split('|')))"#) == "pix=1;")
    #expect(try PackedScript.unescape(#"'\x41\u3042'"#) == "Aあ")
}

private struct ArchiveFixture: Provider {
    let urls: [URL]
    let ledger: Ledger

    actor Ledger {
        private(set) var calls = 0
        func record() { calls += 1 }
    }

    func search(_ title: String) async throws -> Manga { Manga(title: title, chapters: [chapter("fixture", number: 1, count: urls.count)]) }
    func pages(_ chapter: Chapter) async throws -> [URL] {
        await ledger.record()
        return urls
    }
}

@Test func archiveReuseRetryRepairAndWarmPDF() async throws {
    let host = "archive-fixture.test"
    let image = fixtureImage()
    let alternate = fixtureImage(red: true)
    FixtureProtocol.routes.register(host) { request, count in
        if request.url!.path == "/one.png", count == 1 { return reply("unavailable", status: 503, headers: ["Retry-After": "0"]) }
        if request.url!.path == "/one.png", count >= 5 { return reply("invalid image") }
        return (200, [:], request.url!.path == "/one.png" ? image : alternate)
    }
    let http = try HTTP(source: .mangadex, retries: true, protocolClasses: [FixtureProtocol.self])
    let output = try temporaryDirectory()
    defer { try? FileManager.default.removeItem(at: output) }
    let urls = ["one.png", "two.png"].map { URL(string: "https://\(host)/\($0)")! }
    let provider = ArchiveFixture(urls: urls, ledger: .init())
    let chapter = try #require(try await provider.search("Fixture").chapters.first)
    let archiver = Archiver(root: output, http: http, provider: provider, pageWorkers: 4, pdf: false, force: false)
    #expect(try await archiver.archive(chapter, name: chapter.id) == .downloaded)
    let images = output.appendingPathComponent("images/fixture")
    let stale = images.appendingPathComponent("20.jpg")
    let owned = images.appendingPathComponent("0.png")
    let note = images.appendingPathComponent("note.txt")
    try image.write(to: stale)
    try image.write(to: note)
    #expect(try await archiver.archive(chapter, name: chapter.id) == .existing)
    #expect(try metadata(stale) == nil)
    #expect(try metadata(note) != nil)
    #expect(FixtureProtocol.routes.count(host, path: "/one.png") == 2)
    try Data("broken".utf8).write(to: owned)
    #expect(try await archiver.archive(chapter, name: chapter.id) == .downloaded)
    #expect(try Data(contentsOf: owned) == image)

    let pdfArchiver = Archiver(root: output, http: http, provider: provider, pageWorkers: 4, pdf: true, force: false)
    #expect(try await pdfArchiver.archive(chapter, name: chapter.id) == .downloaded)
    let count = await provider.ledger.calls
    let pdf = output.appendingPathComponent("pdf/fixture.pdf")
    #expect(pdfPageCount(pdf) == 2)
    let before = try #require(try metadata(pdf))
    #expect(try await pdfArchiver.archive(chapter, name: chapter.id) == .existing)
    #expect(await provider.ledger.calls == count)
    #expect(try metadata(pdf)?.st_ino == before.st_ino)
    #expect(try metadata(output.appendingPathComponent(".images/fixture")) == nil)
    let forced = Archiver(root: output, http: http, provider: provider, pageWorkers: 4, pdf: true, force: true)
    await #expect(throws: MangapyError.self) { try await forced.archive(chapter, name: chapter.id) }
    #expect(try metadata(pdf)?.st_ino == before.st_ino)
}

@Suite(.enabled(if: ProcessInfo.processInfo.environment["MANGAPY_LIVE_TESTS"] == "1"))
struct FanFoxLive {
    private let title = "Boku dake ga Inai Machi"

    @Test func test_fetch_manga() async throws {
        let provider = FanFox(http: try HTTP(source: .fanfox, retries: false))
        #expect(try await !provider.search(title).chapters.isEmpty)
    }

    @Test func test_fetch_manga_chapter_pages() async throws {
        let provider = FanFox(http: try HTTP(source: .fanfox, retries: false))
        let manga = try await provider.search(title)
        let first = try #require(manga.chapters.first(where: { $0.number == 1 }))
        #expect(try await !provider.pages(first).isEmpty)
    }
}

@Suite(.enabled(if: ProcessInfo.processInfo.environment["MANGAPY_LIVE_TESTS"] == "1"))
struct MangaDexLive {
    private let title = "Backstage Lovers"

    @Test func test_fetch_manga() async throws {
        let provider = MangaDex(http: try HTTP(source: .mangadex, retries: false))
        #expect(try await !provider.search(title).chapters.isEmpty)
    }

    @Test func test_fetch_manga_chapter_pages() async throws {
        let provider = MangaDex(http: try HTTP(source: .mangadex, retries: false))
        let manga = try await provider.search(title)
        let chapter = try #require(manga.chapters.first(where: { $0.number == 5 && $0.downloadable }))
        let pages = try await provider.pages(chapter)
        #expect(!pages.isEmpty)
        #expect(pages.count == chapter.count)
    }
}
