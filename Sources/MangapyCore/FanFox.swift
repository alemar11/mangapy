import Foundation
import SwiftSoup

private func captures(_ pattern: String, in value: String) -> [[String]] {
    let regex = try! NSRegularExpression(pattern: pattern)
    return regex.matches(in: value, range: NSRange(value.startIndex..., in: value)).map { match in
        (1..<match.numberOfRanges).map { index in
            Range(match.range(at: index), in: value).map { String(value[$0]) } ?? ""
        }
    }
}

private func capture(_ pattern: String, in value: String) -> String? {
    captures(pattern, in: value).first?.first
}

func legacySlug(_ title: String) -> String {
    title.replacingOccurrences(of: "[^a-zA-Z0-9]+", with: "_", options: .regularExpression)
        .trimmingCharacters(in: CharacterSet(charactersIn: "_")).lowercased()
}

struct FanFox: Provider {
    static let baseURL = URL(string: "https://fanfox.net")!
    let http: HTTP
    var base = Self.baseURL

    func headers(for url: URL) -> [String: String] {
        var headers = ["Referer": base.absoluteString.trimmingCharacters(in: CharacterSet(charactersIn: "/"))]
        if sameOrigin(base, url) { headers["Cookie"] = "isAdult=1" }
        return headers
    }

    private func html(_ url: URL) async throws -> String {
        let bytes = try await http.get(url, headers: headers(for: url))
        return String(decoding: bytes, as: UTF8.self)
    }

    // SwiftSoup nodes stay inside synchronous parsing so they never cross suspension points.
    func parseManga(_ html: String, title: String) throws -> Manga? {
        let doc = try SwiftSoup.parse(html)
        var chapters: [Chapter] = []
        var seen = Set<String>()
        for list in ["list-1", "list-2"] {
            for link in try doc.select("#\(list) ul.detail-main-list a[href]").array() {
                let url = try remoteURL(link.attr("href"), relativeTo: base)
                let segments = URLComponents(url: url, resolvingAgainstBaseURL: false)?.percentEncodedPath.split(separator: "/") ?? []
                guard let segment = segments.reversed().first(where: {
                    $0.first == "c" && $0.dropFirst().utf8.first.map { (48...57).contains($0) } == true
                }) else { continue }
                let id = String(segment.dropFirst())
                guard seen.insert(id).inserted else { continue }
                chapters.append(Chapter(id: id, label: id, number: decimal(id), volume: nil, url: url, count: nil, external: false))
            }
        }
        return chapters.isEmpty ? nil : Manga(title: title, chapters: chapters)
    }

    private func match(_ html: String, title: String) throws -> (name: String, url: URL) {
        let doc = try SwiftSoup.parse(html)
        let query = title.normalizedTitle
        var partial: (String, URL)?
        var suggestions: [String] = []
        for link in try doc.select("ul.manga-list-4-list p.manga-list-4-item-title a[href]").array() {
            let name = try link.text().trimmed
            if !name.isEmpty, suggestions.count < 5 { suggestions.append(name) }
            let candidate = name.normalizedTitle
            if candidate == query { return (name, try remoteURL(link.attr("href"), relativeTo: base)) }
            if partial == nil, !query.isEmpty, candidate.contains(query) {
                partial = (name, try remoteURL(link.attr("href"), relativeTo: base))
            }
        }
        guard let partial else { throw notFound(title, suggestions: suggestions) }
        return partial
    }

    func search(_ title: String) async throws -> Manga {
        do {
            let direct = try endpoint("/manga/\(legacySlug(title))/", at: base)
            if let manga = try await parseManga(html(direct), title: title) { return manga }
        } catch HTTPError.status(404, _) {
            // Fall through to the catalog lookup.
        } catch {
            throw MangapyError("FanFox direct lookup failed: \(error.localizedDescription)")
        }
        let search = try endpoint("/search", at: base, query: [.init(name: "title", value: title)])
        let found = try await match(html(search), title: title)
        guard let manga = try await parseManga(html(found.url), title: found.name) else {
            throw MangapyError("No FanFox chapters found")
        }
        return manga
    }

    private func batches(_ base: URL, cid: String, count: Int, key: String) async throws -> [URL] {
        var pages: [URL] = []
        for page in stride(from: 0, to: count, by: 2) {
            let url = try endpoint("chapterfun.ashx", at: base, query: [
                .init(name: "cid", value: cid),
                .init(name: "page", value: String(page + 1)),
                .init(name: "key", value: key),
            ])
            let script = try await PackedScript.unpack(html(url))
            guard let prefix = capture(#"pix="(.+?)""#, in: script) else {
                throw MangapyError("Missing FanFox image base")
            }
            for path in captures(#""(/\w.+?)""#, in: script) {
                pages.append(try remoteURL(prefix + path[0], relativeTo: base))
            }
        }
        guard pages.count == count else {
            throw MangapyError("FanFox advertised \(count) pages but returned \(pages.count)")
        }
        return pages
    }

    private func inlineMetadata(_ page: String) throws -> (lastPage: Int?, urls: [String]?) {
        let doc = try SwiftSoup.parse(page)
        let last = try doc.select("a[data-page]").array().compactMap { Int(try $0.attr("data-page")) }
            .filter { $0 > 0 }.max()
        for element in try doc.select("script").array() {
            if let script = try? PackedScript.unpack(element.data()),
               let list = capture(#"newImgs\s*=\s*\[([^\]]+)\]"#, in: script) {
                return (last, list.split(separator: ",", omittingEmptySubsequences: false).map { String($0).trimmed })
            }
        }
        return (last, nil)
    }

    func pages(_ chapter: Chapter) async throws -> [URL] {
        let page = try await html(chapter.url)
        let cid = capture(#"chapterid\s*=\s*(\d+)"#, in: page)
        let count = capture(#"imagecount\s*=\s*(\d+)"#, in: page).flatMap(Int.init).flatMap { $0 > 0 ? $0 : nil }
        let metadata = try inlineMetadata(page)
        var batchError: Error?
        if let cid, let count {
            do { return try await batches(chapter.url, cid: cid, count: count, key: "") }
            catch { try Task.checkCancellation(); batchError = error }
        }
        let key = (try? PackedScript.unpack(page))
            .flatMap { capture(#"var guidkey=(.*?)';"#, in: $0) }?
            .filter { !"'+\\".contains($0) } ?? ""
        if let cid, let count, !key.isEmpty {
            do { return try await batches(chapter.url, cid: cid, count: count, key: key) }
            catch { try Task.checkCancellation(); batchError = error }
        }
        if let last = metadata.lastPage, last != count {
            guard let cid else { throw MangapyError("Missing FanFox chapter ID") }
            do { return try await batches(chapter.url, cid: cid, count: last, key: key) }
            catch { try Task.checkCancellation(); batchError = error }
        }
        if let urls = metadata.urls {
            return try urls.map { try remoteURL(PackedScript.unescape($0), relativeTo: chapter.url) }
        }
        throw batchError ?? MangapyError("No FanFox images found")
    }
}

enum PackedScript {
    private static let alphabet = Array("0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ")
    private static let maxSize = 8 * 1024 * 1024

    static func unpack(_ content: String) throws -> String {
        let pattern = #"\}\(\s*('(?:[^'\\]|\\.)*'|"(?:[^"\\]|\\.)*")\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*('(?:[^'\\]|\\.)*'|"(?:[^"\\]|\\.)*")\.split\(\s*['"]\|['"]\s*\)"#
        guard let args = captures(pattern, in: content).first,
              let radix = Int(args[1]), let count = Int(args[2]) else {
            throw MangapyError("Missing packed FanFox script")
        }
        var script = try unescape(args[0])
        let dictionary = try unescape(args[3])
        let words = dictionary.split(separator: "|", omittingEmptySubsequences: false)
        guard (2...alphabet.count).contains(radix), count <= words.count else {
            throw MangapyError("Invalid FanFox packer dictionary")
        }
        for index in (0..<count).reversed() where !words[index].isEmpty {
            var value = index
            var digits: [Character] = []
            repeat {
                digits.append(alphabet[value % radix])
                value /= radix
            } while value > 0
            let token = String(digits.reversed())
            let regex = try NSRegularExpression(pattern: "\\b\(token)\\b")
            let replacement = NSRegularExpression.escapedTemplate(for: String(words[index]))
            script = regex.stringByReplacingMatches(in: script, range: NSRange(script.startIndex..., in: script), withTemplate: replacement)
            guard script.utf8.count <= maxSize else { throw MangapyError("FanFox script exceeded unpack size limit") }
        }
        return script
    }

    static func unescape(_ quoted: String) throws -> String {
        let text = quoted.unicodeScalars
        guard text.count >= 2, let quote = text.first, quote == "'" || quote == "\"", text.last == quote else {
            throw MangapyError("Invalid JavaScript string")
        }
        var scalars = text.dropFirst().dropLast().makeIterator()
        var result = String.UnicodeScalarView()
        while let scalar = scalars.next() {
            if scalar != "\\" { result.append(scalar); continue }
            guard let escaped = scalars.next() else { throw MangapyError("Incomplete JavaScript escape") }
            switch escaped {
            case "n": result.append("\n")
            case "r": result.append("\r")
            case "t": result.append("\t")
            case "b": result.append("\u{08}")
            case "f": result.append("\u{0c}")
            case "v": result.append("\u{0b}")
            case "0": result.append("\0")
            case "\n": break
            case "x", "u":
                var hex = String.UnicodeScalarView()
                for _ in 0..<(escaped == "x" ? 2 : 4) {
                    guard let digit = scalars.next() else { throw MangapyError("Incomplete JavaScript Unicode escape") }
                    hex.append(digit)
                }
                guard let value = UInt32(String(hex), radix: 16), let decoded = Unicode.Scalar(value) else {
                    throw MangapyError("Invalid Unicode escape")
                }
                result.append(decoded)
            default: result.append(escaped)
            }
        }
        return String(result)
    }
}
