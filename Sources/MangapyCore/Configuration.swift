import Foundation
import Yams

private struct Fields {
    private(set) var values: [String: Node] = [:]
    private(set) var keys: [String] = []

    init(_ node: Node, context: String) throws {
        guard let mapping = node.mapping else { throw MangapyError("Expected a mapping for \(context)") }
        for (key, value) in mapping {
            guard key.tag.rawValue == Tag.Name.str.rawValue, let name = key.string else {
                throw MangapyError("Expected string keys in \(context)")
            }
            guard values.updateValue(value, forKey: name) == nil else {
                throw MangapyError("Duplicate field: \(name)")
            }
            keys.append(name)
        }
    }

    subscript(_ key: String) -> Node? { values[key] }

    mutating func remove(_ key: String) -> Node? { values.removeValue(forKey: key) }

    func check(_ allowed: Set<String>) throws {
        if let key = keys.first(where: { values[$0] != nil && !allowed.contains($0) }) {
            throw MangapyError("Unknown field: \(key)")
        }
    }

    func string(_ key: String) throws -> String? {
        guard let value = self[key] else { return nil }
        return try Self.string(value, field: key)
    }

    private static func string(_ value: Node, field: String) throws -> String {
        guard value.tag.rawValue == Tag.Name.str.rawValue, let text = value.string else {
            throw MangapyError("Expected a string for \(field)")
        }
        return text
    }

    func bool(_ key: String) throws -> Bool? {
        guard let value = self[key] else { return nil }
        guard value.tag.rawValue == Tag.Name.bool.rawValue, let result = value.bool else {
            throw MangapyError("Expected a boolean for \(key)")
        }
        return result
    }

    func chapter(_ key: String) throws -> String? {
        guard let value = self[key], value.null == nil else { return nil }
        if [Tag.Name.int.rawValue, Tag.Name.float.rawValue].contains(value.tag.rawValue),
           let number = value.int.map(Double.init) ?? value.float, number.isFinite {
            return decimalLabel(number)
        }
        return try Self.string(value, field: key)
    }

    func list(_ key: String) throws -> [String]? {
        guard let value = self[key] else { return nil }
        let nodes = value.sequence.map(Array.init) ?? [value]
        let items = try nodes.map { try Self.string($0, field: key).trimmed }
        guard !items.isEmpty, items.allSatisfy({ !$0.isEmpty }) else {
            throw MangapyError("Expected a non-empty string or list for \(key)")
        }
        return items
    }

    func proxy() throws -> Proxy? {
        guard let value = self["proxy"], value.null == nil else { return nil }
        let proxy = try Fields(value, context: "proxy")
        try proxy.check(["http", "https"])
        guard let http = try proxy.string("http"), let https = try proxy.string("https") else {
            throw MangapyError("Expected both http and https proxy URLs")
        }
        return Proxy(http: http, https: https)
    }
}

struct YAMLConfiguration {
    private static let defaultKeys: Set<String> = ["output", "debug", "proxy", "force", "no_retry", "no_progress"]
    private static let entryKeys = defaultKeys.union([
        "title", "source", "pdf", "download_all_chapters", "download_last_chapter", "download_single_chapter",
        "download_chapters", "translated_language", "content_rating", "data_saver",
    ])
    private static let resolver = try! Resolver.default
        .removing(.timestamp).removing(.value).removing(.merge)
        .replacing(.bool, with: "^(?:true|True|TRUE|false|False|FALSE)$")

    private struct Defaults {
        let output: String?
        let debug: Bool
        let proxy: Proxy?
        let force: Bool
        let noRetry: Bool
        let noProgress: Bool

        init(_ fields: Fields) throws {
            try fields.check(YAMLConfiguration.defaultKeys)
            output = try fields.string("output")
            debug = try fields.bool("debug") ?? false
            proxy = try fields.proxy()
            force = try fields.bool("force") ?? false
            noRetry = try fields.bool("no_retry") ?? false
            noProgress = try fields.bool("no_progress") ?? false
        }
    }

    private let entries: [(Node, Source?)]
    private let defaults: Defaults
    var indices: Range<Int> { entries.indices }

    init(text: String) throws {
        guard let node = try Yams.compose(yaml: text, Self.resolver) else {
            throw MangapyError("YAML contains no downloads")
        }
        var root = try Fields(node, context: "configuration")
        let downloads = root.remove("downloads")
        var entries: [(Node, Source?)] = []
        var groups = Set<Source>()
        for key in root.keys {
            guard let source = Source(argument: key), let group = root.remove(key) else { continue }
            guard downloads == nil else { throw MangapyError("downloads cannot be combined with legacy provider groups") }
            guard groups.insert(source).inserted else { throw MangapyError("Duplicate provider group") }
            guard let sequence = group.sequence else { throw MangapyError("Expected a list for \(key)") }
            entries += sequence.map { ($0, source) }
        }
        if let downloads {
            guard let sequence = downloads.sequence else { throw MangapyError("Expected a list for downloads") }
            entries = sequence.map { ($0, nil) }
        }
        guard !entries.isEmpty else { throw MangapyError("YAML contains no downloads") }
        guard entries.allSatisfy({ $0.0.mapping != nil }) else { throw MangapyError("Every download must be a mapping") }
        self.entries = entries
        self.defaults = try Defaults(root)
    }

    func request(at index: Int) throws -> DownloadRequest {
        let (node, groupSource) = entries[index]
        let entry = try Fields(node, context: "download")
        try entry.check(Self.entryKeys)
        let source: Source
        if let name = try entry.string("source") {
            guard let parsed = Source(argument: name) else { throw MangapyError("Unknown source: \(name)") }
            source = parsed
        } else {
            source = groupSource ?? .fanfox
        }
        var selectors: [Selection] = []
        if try entry.bool("download_all_chapters") == true { selectors.append(.all) }
        if try entry.bool("download_last_chapter") == true { selectors.append(.latest) }
        if let single = try entry.chapter("download_single_chapter") { selectors.append(.single(single)) }
        if let range = try entry.chapter("download_chapters") { selectors.append(try .parseRange(range)) }
        guard selectors.count <= 1 else { throw MangapyError("Chapter selection fields are mutually exclusive") }

        let languages = try entry.list("translated_language")
        let ratings = try entry.list("content_rating")
        let dataSaver = try entry.bool("data_saver")
        if source != .mangadex, languages != nil || ratings != nil || dataSaver != nil {
            throw MangapyError("translated_language, content_rating and data_saver require MangaDex")
        }
        var request = try DownloadRequest(
            title: entry.string("title") ?? "",
            output: entry.string("output") ?? defaults.output,
            selection: selectors.first ?? .latest,
            source: source,
            proxy: entry["proxy"] == nil ? defaults.proxy : entry.proxy(),
            retries: !(entry.bool("no_retry") ?? defaults.noRetry),
            debug: entry.bool("debug") ?? defaults.debug,
            pdf: entry.bool("pdf") ?? false,
            force: entry.bool("force") ?? defaults.force,
            showProgress: !(entry.bool("no_progress") ?? defaults.noProgress)
        )
        if let languages { request.mangaDex.languages = languages }
        if let ratings { request.mangaDex.ratings = ratings }
        if let dataSaver { request.mangaDex.dataSaver = dataSaver }
        return request
    }
}

public func runConfiguration(at path: String) async throws {
    let config = try YAMLConfiguration(text: String(contentsOfFile: path, encoding: .utf8))
    var failures = 0
    for index in config.indices {
        do { try await config.request(at: index).run() }
        catch {
            try Task.checkCancellation()
            writeError("Download entry \(index + 1): \(error.localizedDescription)")
            failures += 1
        }
    }
    if failures > 0 { throw MangapyError("\(failures) download(s) incomplete") }
}
