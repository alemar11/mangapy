import CoreGraphics
import Foundation
import ImageIO
import Testing
import UniformTypeIdentifiers
@testable import MangapyCore

func temporaryDirectory() throws -> URL {
    let path = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
    return try directory(path)
}

func chapter(_ id: String, number: Double?, volume: Double? = nil, count: Int? = 1) -> Chapter {
    Chapter(id: id, label: id, number: number, volume: volume, url: URL(string: "https://fixture.test/at-home/server/\(id)")!,
            count: count, external: false)
}

@Test func chapterSelectionAndOutputNames() throws {
    let uuid = "12345678-1234-4abc-aaaa-abcd1234abcd"
    let chapters = [
        chapter("special-edition", number: nil),
        chapter("late", number: 2.5, volume: 2),
        chapter("early", number: 2.5, volume: 1),
        chapter("missing", number: 9, count: 0),
        chapter(uuid, number: 1),
    ].sorted(by: Chapter.precedes)
    #expect(Selection.latest.select(chapters).map(\.id) == ["early"])
    #expect(try Selection(argument: uuid).select(chapters).map(\.id) == [uuid])
    #expect(try Selection(argument: "special-edition").select(chapters).map(\.id) == ["special-edition"])
    #expect(try Selection(argument: "1-2.5").select(chapters).map(\.id) == [uuid, "early", "late"])
    #expect(try Selection(argument: "9-").select(chapters).map(\.id) == ["missing"])
    #expect(throws: MangapyError.self) { try Selection.parseRange("5-3") }
    #expect(throws: MangapyError.self) { try Selection.parseRange("NaN-3") }
    #expect(chapterName(chapters[1], source: .fanfox) == "2.5")
    #expect(outputComponent(" ｜ＣＯＮ.txt/ ") == "_CON.txt")
    #expect(outputComponent(String(repeating: "雪", count: 100)).utf8.count <= 180)
    #expect(decimalLabel(1e-10) == "0.0000000001")
    #expect(decimal("0x1.0p2") == nil)
    #expect(throws: MangapyError.self) { try DownloadRequest(title: "Example", output: "bad\0path") }
}

@Test func existingYAMLAndLegacyDefaults() throws {
    let root = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
    let samples = root.appendingPathComponent("samples")
    for file in try FileManager.default.contentsOfDirectory(at: samples, includingPropertiesForKeys: nil)
        where file.pathExtension == "yaml" {
        let config = try YAMLConfiguration(text: String(contentsOf: file, encoding: .utf8))
        for index in config.indices { _ = try config.request(at: index) }
    }
    let config = try YAMLConfiguration(text: """
        output: ~/manga
        no_progress: true
        proxy: {http: 'http://localhost:8888', https: 'http://localhost:8888'}
        FanFox:
          - title: Example
            download_single_chapter: 10.5
        MangaDex:
          - title: Translation
            proxy: null
            translated_language: [en, ja]
            content_rating: safe
            data_saver: true
            download_chapters: 2.5-
        """)
    let fanfox = try config.request(at: 0)
    let mangadex = try config.request(at: 1)
    #expect(fanfox.source == .fanfox)
    #expect(fanfox.proxy != nil)
    #expect(fanfox.selection.select([chapter("alias", number: 10.5)]).count == 1)
    #expect(mangadex.output == FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("manga"))
    #expect(mangadex.proxy == nil)
    #expect(!mangadex.showProgress)
    #expect(mangadex.mangaDex.languages == ["en", "ja"])
    #expect(mangadex.mangaDex.ratings == ["safe"])
    #expect(mangadex.mangaDex.dataSaver)
}

@Test func yamlRejectsMalformedFieldsAndConflictingSelectors() throws {
    for yaml in ["FanFox: []\ndownloads: []", "unexpected: true\ndownloads: [{title: Example}]", "downloads: [Example]",
                 "downloads: [{title: Example}]\n---\nfoo: 2", "force: true\nforce: false\ndownloads: [{title: Example}]"] {
        #expect(throws: (any Error).self) { try YAMLConfiguration(text: yaml) }
    }
    for fields in ["force: null", "force: yes", "data_saver: true", "unknown: true",
                   "download_all_chapters: true, download_single_chapter: 2",
                   "source: mangadex, translated_language: [en, 3]"] {
        let config = try YAMLConfiguration(text: "downloads: [{title: Example, \(fields)}]")
        #expect(throws: MangapyError.self) { try config.request(at: 0) }
    }
}

@Test func outputRejectsSymlinks() throws {
    let root = try temporaryDirectory()
    defer { try? FileManager.default.removeItem(at: root) }
    let outside = try directory(root.appendingPathComponent("outside"))
    let output = try directory(root.appendingPathComponent("output"))
    let source = output.appendingPathComponent("fanfox")
    try FileManager.default.createSymbolicLink(at: source, withDestinationURL: outside)
    #expect(throws: MangapyError.self) { try mangaDirectory(at: output, source: .fanfox, title: "Title") }
    let path = output.appendingPathComponent("0.jpg")
    try FileManager.default.createSymbolicLink(at: path, withDestinationURL: outside.appendingPathComponent("missing"))
    #expect(throws: MangapyError.self) { try regularFileExists(path) }
    #expect(try FileManager.default.contentsOfDirectory(atPath: outside.path).isEmpty)
}

@Test func outputLockSerializesConcurrentWriters() async throws {
    let root = try temporaryDirectory()
    defer { try? FileManager.default.removeItem(at: root) }
    let ledger = LockLedger()
    async let left: Void = checkLock(root, ledger: ledger)
    async let right: Void = checkLock(root, ledger: ledger)
    _ = try await (left, right)
    #expect(await ledger.peak == 1)
}

private actor LockLedger {
    private var active = 0
    private(set) var peak = 0

    func begin() {
        active += 1
        peak = max(peak, active)
    }

    func end() { active -= 1 }
}

private func checkLock(_ root: URL, ledger: LockLedger) async throws {
    try await withMangaLock(at: root) {
        await ledger.begin()
        try await Task.sleep(for: .milliseconds(100))
        await ledger.end()
    }
}

func fixtureImage(type: UTType = .png, orientation: Int = 1, red: Bool = false) -> Data {
    let context = CGContext(data: nil, width: 4, height: 6, bitsPerComponent: 8, bytesPerRow: 0,
                            space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)!
    context.setFillColor(red: red ? 1 : 0, green: 0.2, blue: 0.8, alpha: 1)
    context.fill(CGRect(x: 0, y: 0, width: 4, height: 6))
    let data = NSMutableData()
    let writer = CGImageDestinationCreateWithData(data, type.identifier as CFString, 1, nil)!
    CGImageDestinationAddImage(writer, context.makeImage()!, [kCGImagePropertyOrientation: orientation] as CFDictionary)
    precondition(CGImageDestinationFinalize(writer))
    return data as Data
}

@Test func pdfHasValidatedOrderedPagesAndAppliesOrientation() throws {
    let output = try temporaryDirectory()
    defer { try? FileManager.default.removeItem(at: output) }
    let first = output.appendingPathComponent("first.jpg")
    let second = output.appendingPathComponent("second.png")
    let destination = output.appendingPathComponent("chapter.pdf")
    let jpeg = fixtureImage(type: .jpeg, orientation: 6)
    try jpeg.write(to: first)
    try fixtureImage().write(to: second)
    try writePDF([first, second], to: destination)
    let pdf = try #require(CGPDFDocument(destination as CFURL))
    #expect(pdf.numberOfPages == 2)
    let page = try #require(pdf.page(at: 1)).getBoxRect(.mediaBox)
    let next = try #require(pdf.page(at: 2)).getBoxRect(.mediaBox)
    #expect(abs(page.width - next.height) < 0.001)
    #expect(abs(page.height - next.width) < 0.001)
    #expect(throws: MangapyError.self) { try decodeImage(Data(jpeg.dropLast(jpeg.count / 2))) }
    let original = try Data(contentsOf: destination)
    try Data("corrupt".utf8).write(to: second)
    #expect(throws: MangapyError.self) { try writePDF([first, second], to: destination) }
    #expect(try Data(contentsOf: destination) == original)
    #expect(try FileManager.default.contentsOfDirectory(atPath: output.path).count == 3)
}
