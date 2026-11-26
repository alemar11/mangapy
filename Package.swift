// swift-tools-version: 6.4.0
import PackageDescription

let package = Package(
    name: "Mangapy",
    platforms: [.macOS(.v13)],
    products: [.executable(name: "mangapy", targets: ["MangapyCLI"])],
    dependencies: [
        .package(url: "https://github.com/apple/swift-argument-parser.git", from: "1.8.2"),
        .package(url: "https://github.com/jpsim/Yams.git", from: "6.2.2"),
        .package(url: "https://github.com/scinfu/SwiftSoup.git", from: "2.11.3"),
    ],
    targets: [
        .target(name: "MangapyCore", dependencies: ["Yams", "SwiftSoup"]),
        .executableTarget(name: "MangapyCLI", dependencies: [
            "MangapyCore",
            .product(name: "ArgumentParser", package: "swift-argument-parser"),
        ]),
        .testTarget(name: "MangapyCoreTests", dependencies: ["MangapyCore"], path: "tests/MangapyCoreTests"),
    ]
)
