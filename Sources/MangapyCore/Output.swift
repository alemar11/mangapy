import CryptoKit
import Darwin
import Foundation

func digest(_ value: String) -> String {
    SHA256.hash(data: Data(value.utf8)).prefix(6).map { String(format: "%02x", $0) }.joined()
}

private let unsafeCharacters = CharacterSet(charactersIn: "<>:\"/\\|?*")
private let componentEdges = CharacterSet(charactersIn: " ._")

func outputComponent(_ value: String) -> String {
    let normalized = value.precomposedStringWithCompatibilityMapping
    let sanitized = String(normalized.unicodeScalars.map { scalar -> Character in
        if scalar.properties.generalCategory == .control || unsafeCharacters.contains(scalar) { return "_" }
        if scalar.properties.isWhitespace { return " " }
        return Character(scalar)
    })
    let spaces = sanitized.split(separator: " ").joined(separator: " ")
    let name = spaces.replacingOccurrences(of: "_+", with: "_", options: .regularExpression)
        .trimmingCharacters(in: componentEdges)
    guard !name.isEmpty else { return "unknown" }
    let stem = name.split(separator: ".").first?.uppercased() ?? ""
    let reserved = ["CON", "PRN", "AUX", "NUL"].contains(stem)
        || stem.range(of: "^(COM|LPT)[1-9]$", options: .regularExpression) != nil
    let safe = reserved ? "_" + name : name
    guard safe.utf8.count > 180 else { return safe }
    var prefix = String.UnicodeScalarView()
    var length = 0
    for scalar in safe.unicodeScalars {
        length += scalar.utf8.count
        if length > 167 { break }
        prefix.append(scalar)
    }
    let head = String(prefix).replacingOccurrences(of: "[ ._]+$", with: "", options: .regularExpression)
    return head + "-" + digest(safe)
}

func metadata(_ url: URL) throws -> stat? {
    var info = stat()
    let status = url.withUnsafeFileSystemRepresentation { lstat($0!, &info) }
    if status == 0 { return info }
    if errno == ENOENT { return nil }
    throw POSIXError(POSIXErrorCode(rawValue: errno) ?? .EIO)
}

func isRegular(_ info: stat) -> Bool { info.st_mode & S_IFMT == S_IFREG }

func regularFileExists(_ url: URL) throws -> Bool {
    guard let info = try metadata(url) else { return false }
    guard isRegular(info) else { throw MangapyError("Not a regular file: \(url.path)") }
    return true
}

func directory(_ url: URL, createParents: Bool = false) throws -> URL {
    if try metadata(url) == nil {
        do {
            try FileManager.default.createDirectory(at: url, withIntermediateDirectories: createParents)
        } catch {
            // Another invocation may have created the directory in the meantime.
            guard try metadata(url) != nil else { throw error }
        }
    }
    guard let info = try metadata(url), info.st_mode & S_IFMT == S_IFDIR else {
        throw MangapyError("Not a real directory: \(url.path)")
    }
    return url
}

func mangaDirectory(at root: URL, source: Source, title: String) throws -> URL {
    let root = try directory(root, createParents: true).resolvingSymlinksInPath()
    let source = try directory(root.appendingPathComponent(source.rawValue, isDirectory: true))
    let normalized = title.precomposedStringWithCompatibilityMapping.folding(options: .caseInsensitive, locale: nil)
    let slug = normalized.replacingOccurrences(of: #"\W+"#, with: "_", options: .regularExpression)
        .trimmingCharacters(in: CharacterSet(charactersIn: "_"))
    let name = slug.unicodeScalars.contains(where: { CharacterSet.alphanumerics.contains($0) })
        ? outputComponent(slug) : "manga_" + digest(normalized)
    let preferred = source.appendingPathComponent(name, isDirectory: true)
    let old = legacySlug(title)
    if !old.isEmpty, try metadata(preferred) == nil {
        let legacy = source.appendingPathComponent(old, isDirectory: true)
        if let info = try metadata(legacy), info.st_mode & S_IFMT == S_IFDIR { return legacy }
    }
    return try directory(preferred)
}

func chapterName(_ chapter: Chapter, source: Source) -> String {
    if source == .fanfox, let number = chapter.number { return outputComponent(decimalLabel(number)) }
    return outputComponent(chapter.id)
}

func withMangaLock<T>(at directory: URL, _ work: () async throws -> T) async throws -> T {
    let url = directory.appendingPathComponent(".mangapy.lock")
    _ = try regularFileExists(url)
    let fd = url.withUnsafeFileSystemRepresentation { open($0!, O_WRONLY | O_CREAT | O_NOFOLLOW | O_CLOEXEC | O_NONBLOCK, 0o644) }
    guard fd >= 0 else { throw POSIXError(POSIXErrorCode(rawValue: errno) ?? .EIO) }
    defer { close(fd) }
    var info = stat()
    guard fstat(fd, &info) == 0, isRegular(info) else { throw MangapyError("Not a regular file: \(url.path)") }
    while flock(fd, LOCK_EX | LOCK_NB) != 0 {
        guard errno == EWOULDBLOCK || errno == EINTR else {
            throw POSIXError(POSIXErrorCode(rawValue: errno) ?? .EIO)
        }
        try await Task.sleep(for: .milliseconds(50))
    }
    return try await work()
}
