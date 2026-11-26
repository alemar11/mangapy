import ArgumentParser
import Darwin
import Dispatch
import Foundation
import MangapyCore

@main
struct Mangapy: AsyncParsableCommand {
    static let configuration = CommandConfiguration(
        commandName: "mangapy",
        abstract: "Manga downloader for FanFox and MangaDex",
        version: "mangapy 4.1.2",
        subcommands: [Title.self, YAML.self]
    )

    static func main() async {
        let arguments = Array(CommandLine.arguments.dropFirst())

        signal(SIGINT, SIG_IGN)
        let interrupt = DispatchSource.makeSignalSource(signal: SIGINT, queue: .global())
        interrupt.setEventHandler { Darwin.exit(130) }
        interrupt.resume()
        defer { interrupt.cancel() }

        guard !arguments.isEmpty else { usageFailure(helpMessage()) }
        do {
            var command = try await asyncParseAsRoot(arguments == ["-v"] ? ["--version"] : arguments)
            if var command = command as? AsyncParsableCommand {
                try await command.run()
            } else {
                try command.run()
            }
        } catch {
            if exitCode(for: error) == .validationFailure { usageFailure(fullMessage(for: error)) }
            exit(withError: error)
        }
    }

    private static func usageFailure(_ message: String) -> Never {
        FileHandle.standardError.write(Data((message + "\n").utf8))
        Darwin.exit(2)
    }

    struct Title: AsyncParsableCommand {
        static let configuration = CommandConfiguration(abstract: "Download a manga by title.")

        @Argument(help: "Manga title to look up.") var mangaTitle: String
        @Option(name: .shortAndLong, help: "Manga provider (fanfox or mangadex).") var source = "fanfox"
        @Option(name: .shortAndLong, help: "Output directory (defaults to ~/Downloads/mangapy).") var out: String?
        @Flag(name: .shortAndLong, help: "Show detailed chapter errors.") var debug = false
        @Flag(help: "Create one PDF per chapter.") var pdf = false
        @Flag(help: "Redownload and replace existing chapter files.") var force = false
        @Flag(help: "Disable network retries.") var noRetry = false
        @Flag(help: "Hide search and chapter progress messages.") var noProgress = false
        @Option(name: .shortAndLong, help: "JSON object with http and https proxy URLs.") var proxy: String?
        @Flag(name: .shortAndLong, help: "Download every chapter.") var all = false
        @Option(name: .shortAndLong, help: "Chapter or range (10, 10-13, or 10-). Defaults to the latest.")
        var chapter: String?

        mutating func validate() throws {
            if all && chapter != nil { throw ValidationError("--all cannot be used with --chapter") }
            if Source(argument: source) == nil { throw ValidationError("Unknown source: \(source)") }
        }

        func run() async throws {
            guard let provider = Source(argument: source) else { throw ValidationError("Unknown source: \(source)") }
            let selection = try chapter.map(Selection.init(argument:)) ?? (all ? .all : .latest)
            let request = try DownloadRequest(
                title: mangaTitle, output: out, selection: selection, source: provider,
                proxy: proxy.map(Proxy.init(json:)), retries: !noRetry, debug: debug,
                pdf: pdf, force: force, showProgress: !noProgress
            )
            try await request.run()
        }
    }

    struct YAML: AsyncParsableCommand {
        static let configuration = CommandConfiguration(commandName: "yaml", abstract: "Run downloads from a YAML file.")

        @Argument(help: "YAML configuration file.") var yamlFile: String

        func run() async throws { try await runConfiguration(at: yamlFile) }
    }
}
