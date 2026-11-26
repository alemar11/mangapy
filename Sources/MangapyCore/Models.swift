import Foundation

struct MangapyError: LocalizedError {
    let message: String

    init(_ message: String) { self.message = message }

    var errorDescription: String? { message }
}

extension String {
    var trimmed: String { trimmingCharacters(in: .whitespacesAndNewlines) }

    var normalizedTitle: String {
        String(lowercased().unicodeScalars.filter { CharacterSet.alphanumerics.contains($0) })
    }
}

func decimal(_ value: String) -> Double? {
    let value = value.trimmed
    guard !value.contains("x"), !value.contains("X"),
          let number = Double(value), number.isFinite else { return nil }
    return number
}

func decimalLabel(_ number: Double) -> String {
    // Swift uses scientific notation in places where Rust's Display expands it.
    let parts = String(number).split(separator: "e")
    let mantissa = String(parts[0])
    guard parts.count == 2, let exponent = Int(parts[1]) else {
        return mantissa.hasSuffix(".0") ? String(mantissa.dropLast(2)) : mantissa
    }
    let negative = mantissa.hasPrefix("-")
    let unsigned = negative ? String(mantissa.dropFirst()) : mantissa
    let fraction = unsigned.split(separator: ".")
    let digits = fraction.joined()
    let position = fraction[0].count + exponent
    let sign = negative ? "-" : ""
    if position <= 0 {
        return sign + "0." + String(repeating: "0", count: -position) + digits
    }
    if position >= digits.count {
        return sign + digits + String(repeating: "0", count: position - digits.count)
    }
    return sign + digits.prefix(position) + "." + digits.dropFirst(position)
}

public enum Source: String, Sendable {
    case fanfox, mangadex

    public init?(argument: String) { self.init(rawValue: argument.trimmed.lowercased()) }

    var chapterWorkers: Int { self == .mangadex ? 2 : 1 }
    var pageWorkers: Int { self == .mangadex ? 4 : 1 }
    var userAgent: String {
        switch self {
        case .fanfox:
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36"
        case .mangadex:
            "mangapy"
        }
    }
}

struct Chapter: Sendable {
    let id: String
    let label: String
    let number: Double?
    let volume: Double?
    let url: URL
    let count: Int?
    let external: Bool

    var downloadable: Bool { !external && count != 0 }

    private var order: (Int, Double, Double, String) {
        if let number { return (0, volume ?? number, number, label) }
        if let volume { return (1, volume, 0, label) }
        return (2, 0, 0, label)
    }

    static func precedes(_ lhs: Self, _ rhs: Self) -> Bool { lhs.order < rhs.order }
}

struct Manga: Sendable {
    let title: String
    let chapters: [Chapter]
}

public enum Selection: Sendable {
    case all, latest, single(String), range(Double, Double?)

    public init(argument: String) throws {
        if UUID(uuidString: argument) != nil {
            self = .single(argument)
        } else if let separator = argument.firstIndex(of: "-"),
                  decimal(String(argument[..<separator])) != nil {
            self = try .parseRange(argument)
        } else {
            self = .single(argument)
        }
    }

    static func parseRange(_ value: String) throws -> Self {
        guard let separator = value.firstIndex(of: "-") else {
            throw MangapyError("Expected chapter range START-END")
        }
        guard let first = decimal(String(value[..<separator])) else {
            throw MangapyError("Invalid range start")
        }
        let end = String(value[value.index(after: separator)...]).trimmed
        guard !end.isEmpty else { return .range(first, nil) }
        guard let last = decimal(end) else { throw MangapyError("Invalid range end") }
        guard last >= first else { throw MangapyError("Range end precedes its start") }
        return .range(first, last)
    }

    func select(_ chapters: [Chapter]) -> [Chapter] {
        switch self {
        case .all:
            return chapters
        case .latest:
            let available = chapters.filter(\.downloadable)
            let latest = available.filter { $0.number != nil }.max { ($0.number ?? 0) < ($1.number ?? 0) }
            return (latest ?? available.last).map { [$0] } ?? []
        case .single(let label):
            let label = label.trimmed
            let wanted = decimal(label)
            return chapters.first {
                $0.id == label || $0.label == label || (wanted != nil && $0.number == wanted)
            }.map { [$0] } ?? []
        case .range(let start, let end):
            return chapters.filter { chapter in
                guard let number = chapter.number else { return false }
                return number >= start && number <= (end ?? .infinity)
            }
        }
    }
}

public struct Proxy: Sendable, Decodable {
    let http: String
    let https: String

    public init(json: String) throws {
        let data = Data(json.utf8)
        guard let fields = try JSONSerialization.jsonObject(with: data) as? [String: String],
              Set(fields.keys) == ["http", "https"] else {
            throw MangapyError("Expected a JSON object with http and https proxy URLs")
        }
        self = try JSONDecoder().decode(Self.self, from: data)
    }

    init(http: String, https: String) {
        self.http = http
        self.https = https
    }
}

struct MangaDexOptions: Sendable {
    var languages = ["en"]
    var ratings = ["safe", "suggestive", "erotica"]
    var dataSaver = false
}

public struct DownloadRequest: Sendable {
    let title: String
    let output: URL
    let selection: Selection
    let source: Source
    let proxy: Proxy?
    let retries: Bool
    let debug: Bool
    let pdf: Bool
    let force: Bool
    let showProgress: Bool
    var mangaDex = MangaDexOptions()

    public init(
        title: String, output: String? = nil, selection: Selection = .latest, source: Source = .fanfox,
        proxy: Proxy? = nil, retries: Bool = true, debug: Bool = false, pdf: Bool = false,
        force: Bool = false, showProgress: Bool = true
    ) throws {
        guard !title.trimmed.isEmpty else { throw MangapyError("Title must be non-empty") }
        self.title = title.trimmed
        self.output = try Self.outputURL(output)
        self.selection = selection
        self.source = source
        self.proxy = proxy
        self.retries = retries
        self.debug = debug
        self.pdf = pdf
        self.force = force
        self.showProgress = showProgress
    }

    private static func outputURL(_ value: String?) throws -> URL {
        let home = FileManager.default.homeDirectoryForCurrentUser
        guard let path = value?.trimmed else { return home.appendingPathComponent("Downloads/mangapy") }
        guard !path.isEmpty else { throw MangapyError("Output must be non-empty") }
        guard !path.utf8.contains(0) else { throw MangapyError("Output contains a NUL byte") }
        if path == "~" { return home }
        if path.hasPrefix("~/") { return home.appendingPathComponent(String(path.dropFirst(2))) }
        return URL(fileURLWithPath: path)
    }
}
