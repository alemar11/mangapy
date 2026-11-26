import Foundation
import Network

enum HTTPError: LocalizedError {
    case invalidURL, invalidResponse, status(Int, URL)

    var errorDescription: String? {
        switch self {
        case .invalidURL: "Invalid HTTP URL"
        case .invalidResponse: "Invalid HTTP response"
        case .status(let status, let url): "HTTP \(status) for \(url.host ?? "")\(url.path)"
        }
    }
}

func isHTTP(_ url: URL) -> Bool {
    ["http", "https"].contains(url.scheme?.lowercased()) && url.host?.isEmpty == false
}

func remoteURL(_ value: String, relativeTo base: URL? = nil) throws -> URL {
    guard let url = URL(string: value, relativeTo: base)?.absoluteURL, isHTTP(url) else {
        throw HTTPError.invalidURL
    }
    return url
}

func endpoint(_ path: String, at base: URL, query: [URLQueryItem] = []) throws -> URL {
    let url = try remoteURL(path, relativeTo: base)
    guard !query.isEmpty else { return url }
    guard var components = URLComponents(url: url, resolvingAgainstBaseURL: false) else {
        throw HTTPError.invalidURL
    }
    components.queryItems = query
    // Foundation leaves '+' unescaped, while providers decode queries as form data.
    let encoded = components.percentEncodedQuery?.replacingOccurrences(of: "+", with: "%2B")
    components.percentEncodedQuery = encoded
    guard let result = components.url else { throw HTTPError.invalidURL }
    return result
}

func appendingSegments(_ segments: [String], to url: URL) throws -> URL {
    guard var components = URLComponents(url: url, resolvingAgainstBaseURL: false) else {
        throw HTTPError.invalidURL
    }
    let allowed = CharacterSet(charactersIn: "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~")
    var path = components.percentEncodedPath
    if path.hasSuffix("/") { path.removeLast() }
    for segment in segments {
        guard !segment.isEmpty, segment != ".", segment != "..",
              let encoded = segment.addingPercentEncoding(withAllowedCharacters: allowed) else {
            throw HTTPError.invalidURL
        }
        path += "/" + encoded
    }
    components.percentEncodedPath = path
    guard let result = components.url else { throw HTTPError.invalidURL }
    return result
}

private func origin(_ url: URL) -> String {
    let scheme = url.scheme?.lowercased() ?? ""
    let port = url.port ?? (scheme == "https" ? 443 : 80)
    return "\(scheme)://\(url.host?.lowercased() ?? ""):\(port)"
}

private final class Redirects: NSObject, URLSessionTaskDelegate {
    let credential: URLCredential?

    init(credential: URLCredential?) { self.credential = credential }

    func urlSession(
        _ session: URLSession, task: URLSessionTask, willPerformHTTPRedirection response: HTTPURLResponse,
        newRequest request: URLRequest, completionHandler: @escaping @Sendable (URLRequest?) -> Void
    ) {
        completionHandler(nil)
    }

    func urlSession(
        _ session: URLSession, task: URLSessionTask, didReceive challenge: URLAuthenticationChallenge,
        completionHandler: @escaping @Sendable (URLSession.AuthChallengeDisposition, URLCredential?) -> Void
    ) {
        if challenge.protectionSpace.isProxy(), challenge.previousFailureCount == 0, let credential {
            completionHandler(.useCredential, credential)
        } else {
            completionHandler(.performDefaultHandling, nil)
        }
    }
}

actor RequestPacer {
    private let clock = ContinuousClock()
    private var last: ContinuousClock.Instant?

    func wait() async throws {
        while let last {
            let next = last.advanced(by: .milliseconds(500))
            guard clock.now < next else { break }
            try await clock.sleep(until: next)
        }
        last = clock.now
    }
}

final class HTTP: Sendable {
    private let http: URLSession
    private let https: URLSession
    private let retries: Bool

    init(source: Source, retries: Bool, proxy: Proxy? = nil, protocolClasses: [AnyClass]? = nil) throws {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.urlCache = nil
        configuration.urlCredentialStorage = nil
        configuration.httpCookieStorage = nil
        configuration.httpShouldSetCookies = false
        configuration.timeoutIntervalForRequest = 30
        configuration.timeoutIntervalForResource = 30
        configuration.httpMaximumConnectionsPerHost = source.chapterWorkers * source.pageWorkers
        configuration.httpAdditionalHeaders = ["User-Agent": source.userAgent]
        if let protocolClasses { configuration.protocolClasses = protocolClasses }
        if let proxy {
            let httpProxy = try Self.proxyURL(proxy.http)
            let httpsProxy = try Self.proxyURL(proxy.https)
            http = try Self.proxiedSession(configuration, proxy: httpProxy, destination: "HTTP")
            https = try Self.proxiedSession(configuration, proxy: httpsProxy, destination: "HTTPS")
        } else {
            http = URLSession(configuration: configuration, delegate: Redirects(credential: nil), delegateQueue: nil)
            https = http
        }
        self.retries = retries
    }

    deinit {
        http.finishTasksAndInvalidate()
        if https !== http { https.finishTasksAndInvalidate() }
    }

    private static func proxiedSession(
        _ base: URLSessionConfiguration, proxy: URL, destination: String
    ) throws -> URLSession {
        let configuration = base.copy() as! URLSessionConfiguration
        let user = proxy.user(percentEncoded: false)
        let password = proxy.password(percentEncoded: false) ?? ""
        let host = proxy.host!
        let port = proxy.port ?? (proxy.scheme == "https" ? 443 : 80)
        let credential = user.map { URLCredential(user: $0, password: password, persistence: .none) }
        if proxy.scheme == "https" {
            guard #available(macOS 14, *) else { throw MangapyError("TLS proxies require macOS 14 or later") }
            guard let endpointPort = NWEndpoint.Port(rawValue: UInt16(port)) else {
                throw MangapyError("Invalid proxy port")
            }
            let endpoint = NWEndpoint.hostPort(host: .init(host), port: endpointPort)
            let relay = ProxyConfiguration(httpCONNECTProxy: endpoint, tlsOptions: NWProtocolTLS.Options())
            if let user { relay.applyCredential(username: user, password: password) }
            configuration.proxyConfigurations = [relay]
        } else {
            configuration.connectionProxyDictionary = [
                destination + "Enable": 1, destination + "Proxy": host, destination + "Port": port,
                "ExcludeSimpleHostnames": false,
            ]
        }
        return URLSession(configuration: configuration, delegate: Redirects(credential: credential), delegateQueue: nil)
    }

    private static func proxyURL(_ value: String) throws -> URL {
        guard value.hasPrefix("http://") || value.hasPrefix("https://"),
              let url = try? remoteURL(value),
              url.port.map({ (1...65535).contains($0) }) ?? true else {
            throw MangapyError("Invalid proxy URL")
        }
        return url
    }

    func get(_ url: URL, headers: [String: String] = [:], pacer: RequestPacer? = nil) async throws -> Data {
        guard isHTTP(url) else { throw HTTPError.invalidURL }
        var request = URLRequest(url: url, cachePolicy: .reloadIgnoringLocalCacheData)
        for (name, value) in headers { request.setValue(value, forHTTPHeaderField: name) }
        let attempts = retries ? 3 : 1
        for attempt in 0..<attempts {
            try await pacer?.wait()
            var delay = Double(1 << attempt)
            do {
                let (data, response) = try await send(request)
                let status = response.statusCode
                if (200..<300).contains(status) { return data }
                let retryable = status == 429 || (500..<600).contains(status)
                guard retryable && attempt + 1 < attempts else { throw HTTPError.status(status, response.url ?? url) }
                if let raw = response.value(forHTTPHeaderField: "Retry-After"),
                   let seconds = decimal(raw), seconds >= 0 {
                    delay = min(seconds, 30)
                }
            } catch let error as HTTPError {
                throw error
            } catch {
                try Task.checkCancellation()
                guard attempt + 1 < attempts else { throw error }
            }
            try await Task.sleep(for: .seconds(delay))
        }
        throw HTTPError.invalidResponse
    }

    private func send(_ initial: URLRequest) async throws -> (Data, HTTPURLResponse) {
        var request = initial
        for redirects in 0...10 {
            guard let url = request.url else { throw HTTPError.invalidURL }
            let (data, response) = try await (url.scheme == "https" ? https : http).data(for: request)
            guard let response = response as? HTTPURLResponse else { throw HTTPError.invalidResponse }
            guard [301, 302, 303, 307, 308].contains(response.statusCode),
                  let location = response.value(forHTTPHeaderField: "Location") else {
                return (data, response)
            }
            guard redirects < 10 else { throw HTTPError.status(response.statusCode, url) }
            let next = try remoteURL(location, relativeTo: url)
            if !sameOrigin(url, next) {
                request.setValue(nil, forHTTPHeaderField: "Cookie")
                request.setValue(nil, forHTTPHeaderField: "Authorization")
            }
            request.url = next
        }
        throw HTTPError.invalidResponse
    }
}

protocol Provider: Sendable {
    func search(_ title: String) async throws -> Manga
    func pages(_ chapter: Chapter) async throws -> [URL]
    func headers(for url: URL) -> [String: String]
}

extension Provider {
    func headers(for url: URL) -> [String: String] { [:] }
}

func sameOrigin(_ lhs: URL, _ rhs: URL) -> Bool { origin(lhs) == origin(rhs) }

func notFound(_ title: String, suggestions: [String]) -> MangapyError {
    let hint = suggestions.isEmpty ? "" : ". Suggestions: " + suggestions.joined(separator: ", ")
    return MangapyError("Manga not found: \(title)\(hint)")
}
