import CoreGraphics
import Foundation
import ImageIO
import UniformTypeIdentifiers

enum ArchiveStatus { case downloaded, existing, unavailable }

private let managedExtensions: Set<String> = [
    "jpg", "jpeg", "png", "gif", "webp", "bmp", "img", "avif", "tiff", "tif", "heic", "heif",
    "j2k", "jfif", "jp2", "jpe", "jpf", "jpx",
]

func pagePath(in directory: URL, index: Int, url: URL) -> URL {
    let path = URLComponents(url: url, resolvingAgainstBaseURL: false)?.percentEncodedPath ?? ""
    let decoded = path.removingPercentEncoding ?? path
    let suffix = (decoded as NSString).pathExtension.lowercased()
    let valid = suffix.range(of: "^[a-z0-9]{1,10}$", options: .regularExpression) != nil
    return directory.appendingPathComponent("\(index).\(valid ? suffix : "img")")
}

func pruneStale(in directory: URL, keeping expected: [URL]) throws {
    let manager = FileManager.default
    let names = Set(try manager.contentsOfDirectory(atPath: directory.path))
    let exact = Set(expected.map(\.lastPathComponent))
    let folded = Dictionary(uniqueKeysWithValues: expected.map { ($0.lastPathComponent.lowercased(), $0) })
    for name in names where !exact.contains(name) {
        let path = directory.appendingPathComponent(name)
        guard managedExtensions.contains(path.pathExtension.lowercased()),
              path.deletingPathExtension().lastPathComponent.range(of: "^[0-9]+$", options: .regularExpression) != nil,
              let info = try metadata(path), isRegular(info) else { continue }
        if let target = folded[name.lowercased()], !names.contains(target.lastPathComponent),
           let other = try metadata(target), info.st_dev == other.st_dev, info.st_ino == other.st_ino {
            continue
        }
        try manager.removeItem(at: path)
    }
}

private let imageTypes: Set<String> = [
    UTType.jpeg.identifier, UTType.png.identifier, UTType.gif.identifier,
    UTType.webP.identifier, UTType.bmp.identifier, UTType.tiff.identifier,
]

private func decodedImage(_ data: Data, orient: Bool) throws -> (image: CGImage, isJPEG: Bool, orientation: Int) {
    guard let source = CGImageSourceCreateWithData(data as CFData, nil),
          let type = CGImageSourceGetType(source), imageTypes.contains(type as String),
          CGImageSourceGetStatus(source) == .statusComplete else {
        throw MangapyError("Invalid image")
    }
    let properties = CGImageSourceCopyPropertiesAtIndex(source, 0, nil) as? [CFString: Any]
    let orientation = properties?[kCGImagePropertyOrientation] as? Int ?? 1
    var options: [CFString: Any] = [kCGImageSourceShouldCacheImmediately: true]
    let image: CGImage?
    if orient, orientation != 1,
       let width = properties?[kCGImagePropertyPixelWidth] as? Int,
       let height = properties?[kCGImagePropertyPixelHeight] as? Int {
        options[kCGImageSourceCreateThumbnailFromImageAlways] = true
        options[kCGImageSourceCreateThumbnailWithTransform] = true
        options[kCGImageSourceThumbnailMaxPixelSize] = max(width, height)
        image = CGImageSourceCreateThumbnailAtIndex(source, 0, options as CFDictionary)
    } else {
        image = CGImageSourceCreateImageAtIndex(source, 0, options as CFDictionary)
    }
    guard let image, CGImageSourceGetStatusAtIndex(source, 0) == .statusComplete else {
        throw MangapyError("Invalid image")
    }
    return (image, type as String == UTType.jpeg.identifier, orientation)
}

func decodeImage(_ data: Data, orient: Bool = false) throws -> CGImage {
    try decodedImage(data, orient: orient).image
}

func validatePage(_ data: Data, forPDF: Bool) throws -> ValidatedJPEG? {
    let (image, isJPEG, orientation) = try decodedImage(data, orient: false)
    guard forPDF, isJPEG, orientation == 1 else { return nil }
    return ValidatedJPEG(data, image: image)
}

func pdfPageCount(_ url: URL) -> Int? {
    guard let pdf = CGPDFDocument(url as CFURL), !pdf.isEncrypted || pdf.isUnlocked,
          pdf.numberOfPages > 0, pdf.page(at: pdf.numberOfPages) != nil else { return nil }
    return pdf.numberOfPages
}

func writePDF(_ images: [URL], to target: URL, jpegPages: [URL: ValidatedJPEG] = [:]) throws {
    let temporary = target.deletingLastPathComponent().appendingPathComponent(".\(UUID().uuidString).pdf")
    defer { try? FileManager.default.removeItem(at: temporary) }
    let jpeg = images.compactMap { jpegPages[$0] }
    // Quartz handles the whole chapter when any page needs decoding or orientation.
    if jpeg.isEmpty || jpeg.count != images.count {
        try writeQuartzPDF(images, to: temporary)
    } else if try !writeJPEGChapter(zip(images, jpeg), to: temporary) {
        try FileManager.default.removeItem(at: temporary)
        try writeQuartzPDF(images, to: temporary)
    }
    guard pdfPageCount(temporary) == images.count else { throw MangapyError("PDF page count mismatch") }
    let file = try FileHandle(forWritingTo: temporary)
    defer { try? file.close() }
    try file.synchronize()
    _ = try regularFileExists(target)
    let status = temporary.withUnsafeFileSystemRepresentation { source in
        target.withUnsafeFileSystemRepresentation { rename(source!, $0!) }
    }
    guard status == 0 else { throw POSIXError(POSIXErrorCode(rawValue: errno) ?? .EIO) }
}

private func writeQuartzPDF(_ images: [URL], to temporary: URL) throws {
    guard let pdf = CGContext(temporary as CFURL, mediaBox: nil, nil) else {
        throw MangapyError("Could not create PDF")
    }
    defer { pdf.closePDF() }
    for item in images {
        let image = try decodeImage(Data(contentsOf: item, options: .mappedIfSafe), orient: true)
        var page = CGRect(x: 0, y: 0, width: CGFloat(image.width) * 0.72, height: CGFloat(image.height) * 0.72)
        let box = withUnsafeBytes(of: &page) { Data($0) }
        pdf.beginPDFPage([kCGPDFContextMediaBox: box] as CFDictionary)
        pdf.draw(image, in: page)
        pdf.endPDFPage()
    }
}

func batchResults<Item: Sendable, Output: Sendable>(
    _ items: ArraySlice<Item>, operation: @escaping @Sendable (Item) async throws -> Output
) async -> [Result<Output, Error>] {
    await withTaskGroup(of: (Int, Result<Output, Error>).self) { group in
        for (index, item) in items.enumerated() {
            group.addTask {
                do { return (index, .success(try await operation(item))) }
                catch { return (index, .failure(error)) }
            }
        }
        var results = Array<Result<Output, Error>?>(repeating: nil, count: items.count)
        for await (index, result) in group { results[index] = result }
        return results.compactMap { $0 }
    }
}

struct Archiver: Sendable {
    let root: URL
    let http: HTTP
    let provider: any Provider
    let pageWorkers: Int
    let pdf: Bool
    let force: Bool

    func archive(_ chapter: Chapter, name: String) async throws -> ArchiveStatus {
        let pdfPath = try pdf ? directory(root.appendingPathComponent("pdf", isDirectory: true))
            .appendingPathComponent(name + ".pdf") : nil
        let existing: Int? = try pdfPath.flatMap { path in
            guard try regularFileExists(path), !force else { return nil }
            return pdfPageCount(path)
        }
        if let existing, existing == chapter.count || !chapter.downloadable { return .existing }
        guard chapter.downloadable else { return .unavailable }
        let pages = try await provider.pages(chapter)
        if let count = chapter.count, pages.count != count {
            throw MangapyError("Expected \(count) pages, got \(pages.count)")
        }
        guard !pages.isEmpty else { return .unavailable }
        if existing == pages.count { return .existing }

        let folder = try directory(root.appendingPathComponent(pdf ? ".images" : "images", isDirectory: true))
        let chapterDir = try directory(folder.appendingPathComponent(name, isDirectory: true))
        let paths = pages.enumerated().map { pagePath(in: chapterDir, index: $0.offset, url: $0.element) }
        let (downloaded, jpegPages) = try await download(pages: pages, paths: paths)
        if let pdfPath {
            try writePDF(paths, to: pdfPath, jpegPages: jpegPages)
            for path in paths {
                do { try FileManager.default.removeItem(at: path) }
                catch { writeError("Could not remove temporary page \(path.path): \(error.localizedDescription)") }
            }
            // Keep unrelated files and any stale pages from a previous interrupted run.
            _ = chapterDir.withUnsafeFileSystemRepresentation { rmdir($0!) }
            return .downloaded
        }
        try pruneStale(in: chapterDir, keeping: paths)
        return downloaded ? .downloaded : .existing
    }

    private func download(pages: [URL], paths: [URL]) async throws -> (Bool, [URL: ValidatedJPEG]) {
        let jobs = Array(zip(pages, paths))
        var downloaded = false
        var jpegPages: [URL: ValidatedJPEG] = [:]
        var failures: [String] = []
        for start in stride(from: 0, to: jobs.count, by: pageWorkers) {
            try Task.checkCancellation()
            let batch = jobs[start..<min(start + pageWorkers, jobs.count)]
            let results = await batchResults(batch) { try await fetch($0.0, to: $0.1) }
            for ((_, path), result) in zip(batch, results) {
                switch result {
                case .success(let (new, jpeg)):
                    downloaded = downloaded || new
                    jpegPages[path] = jpeg
                case .failure(let error): failures.append("\(path.path): \(error.localizedDescription)")
                }
            }
        }
        try Task.checkCancellation()
        if !failures.isEmpty {
            throw MangapyError("\(failures.count) of \(paths.count) pages failed: \(failures.joined(separator: "; "))")
        }
        return (downloaded, jpegPages)
    }

    private func fetch(_ url: URL, to path: URL) async throws -> (Bool, ValidatedJPEG?) {
        if try regularFileExists(path), !force,
           let cached = try? Data(contentsOf: path, options: .mappedIfSafe) {
            if case .success(let jpeg) = Result(catching: { try validatePage(cached, forPDF: pdf) }) {
                return (false, jpeg)
            }
        }
        let data = try await http.get(url, headers: provider.headers(for: url))
        let jpeg: ValidatedJPEG?
        do { jpeg = try validatePage(data, forPDF: pdf) }
        catch { throw MangapyError("Invalid image for \(path.path)") }
        try data.write(to: path, options: .atomic)
        return (true, jpeg)
    }
}
