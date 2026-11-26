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

func fixtureImage(type: UTType = .png, orientation: Int = 1, red: Bool = false,
                  space: CGColorSpace = CGColorSpaceCreateDeviceRGB()) -> Data {
    let alpha = space.model == .monochrome ? CGImageAlphaInfo.none : .premultipliedLast
    let context = CGContext(data: nil, width: 4, height: 6, bitsPerComponent: 8, bytesPerRow: 0,
                            space: space, bitmapInfo: alpha.rawValue)!
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
    let third = output.appendingPathComponent("third.jpg")
    let destination = output.appendingPathComponent("chapter.pdf")
    let jpeg = fixtureImage(type: .jpeg, orientation: 6)
    let upright = fixtureImage(type: .jpeg)
    try jpeg.write(to: first)
    try fixtureImage().write(to: second)
    try upright.write(to: third)
    let validated = [third: try #require(try validatePage(upright, forPDF: true))]
    #expect(try validatePage(jpeg, forPDF: true) == nil)
    try writePDF([first, second, third], to: destination, jpegPages: validated)
    let pdf = try #require(CGPDFDocument(destination as CFURL))
    #expect(pdf.numberOfPages == 3)
    let page = try #require(pdf.page(at: 1)).getBoxRect(.mediaBox)
    let next = try #require(pdf.page(at: 2)).getBoxRect(.mediaBox)
    #expect(abs(page.width - next.height) < 0.001)
    #expect(abs(page.height - next.width) < 0.001)
    #expect(throws: MangapyError.self) { try decodeImage(Data(jpeg.dropLast(jpeg.count / 2))) }
    let original = try Data(contentsOf: destination)
    try Data("corrupt".utf8).write(to: second)
    #expect(throws: MangapyError.self) { try writePDF([first, second, third], to: destination, jpegPages: validated) }
    #expect(try Data(contentsOf: destination) == original)
    #expect(try FileManager.default.contentsOfDirectory(atPath: output.path).count == 4)
}

@Test func directPDFPreservesJPEGBytesColorAndOrder() throws {
    let output = try temporaryDirectory()
    defer { try? FileManager.default.removeItem(at: output) }
    let spaces = [CGColorSpace(name: CGColorSpace.displayP3)!,
                  CGColorSpace(name: CGColorSpace.genericGrayGamma2_2)!]
    var jpeg = spaces.map { fixtureImage(type: .jpeg, red: true, space: $0) }
    // Some encoders append extra data to the Adobe APP14 segment after the transform.
    let adobeMarker: [UInt8] = [
        0xff, 0xee, 0, 16, 65, 100, 111, 98, 101, 0, 100, 0, 0, 0, 0, 1, 0xff, 0,
    ]
    jpeg[0].insert(contentsOf: adobeMarker, at: 2)
    let paths = [output.appendingPathComponent("b.jpg"), output.appendingPathComponent("a.jpg")]
    var validated: [URL: ValidatedJPEG] = [:]
    for (path, data) in zip(paths, jpeg) {
        try data.write(to: path)
        let descriptor = try validatePage(data, forPDF: true)
        let supported: ValidatedJPEG = try #require(descriptor)
        validated[path] = supported
    }
    let direct = output.appendingPathComponent("direct.pdf")
    let quartz = output.appendingPathComponent("quartz.pdf")
    try writePDF(paths, to: direct, jpegPages: validated)
    try writePDF(paths, to: quartz)
    let directPDF = try #require(CGPDFDocument(direct as CFURL))
    let quartzPDF = try #require(CGPDFDocument(quartz as CFURL))
    #expect(directPDF.numberOfPages == 2)
    for (index, data) in jpeg.enumerated() {
        let page = try #require(directPDF.page(at: index + 1))
        let reference = try #require(quartzPDF.page(at: index + 1))
        #expect(page.getBoxRect(.mediaBox) == reference.getBoxRect(.mediaBox))
        var resources: CGPDFDictionaryRef?
        var objects: CGPDFDictionaryRef?
        var image: CGPDFStreamRef?
        let dictionary = try #require(page.dictionary)
        try #require(CGPDFDictionaryGetDictionary(dictionary, "Resources", &resources))
        let resourcesDictionary = try #require(resources)
        try #require(CGPDFDictionaryGetDictionary(resourcesDictionary, "XObject", &objects))
        let objectDictionary = try #require(objects)
        try #require(CGPDFDictionaryGetStream(objectDictionary, "Im", &image))
        let imageStream = try #require(image)
        var format = CGPDFDataFormat.raw
        let bytes = try #require(CGPDFStreamCopyData(imageStream, &format)) as Data
        #expect(format == .jpegEncoded)
        #expect(bytes == data)
        #expect(try renderPDFPage(page) == renderPDFPage(reference))
    }

    // A cached description must not authorize bytes changed since validation.
    let original = try Data(contentsOf: direct)
    try Data("broken".utf8).write(to: paths[1])
    #expect(throws: MangapyError.self) { try writePDF(paths, to: direct, jpegPages: validated) }
    #expect(try Data(contentsOf: direct) == original)
    #expect(try FileManager.default.contentsOfDirectory(atPath: output.path).count == 4)
}

private func renderPDFPage(_ page: CGPDFPage) throws -> Data {
    let width = 32
    let height = 48
    let context = try #require(CGContext(data: nil, width: width, height: height, bitsPerComponent: 8,
                                         bytesPerRow: width * 4, space: CGColorSpace(name: CGColorSpace.sRGB)!,
                                         bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue))
    let rect = CGRect(x: 0, y: 0, width: width, height: height)
    context.concatenate(page.getDrawingTransform(.mediaBox, rect: rect, rotate: 0, preserveAspectRatio: false))
    context.drawPDFPage(page)
    return Data(bytes: try #require(context.data), count: width * height * 4)
}
