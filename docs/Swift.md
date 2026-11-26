# Swift development

The SwiftPM package builds an arm64 or x86_64 macOS executable for the host
architecture. It requires Swift 6 with the macOS SDK and targets macOS 13 or
later. Swift Testing needs macOS 14 or later. TLS connections to a proxy also
require macOS 14 or later.

```sh
swift build -c release --disable-automatic-resolution
.build/release/mangapy --help
.build/release/mangapy title "Backstage Lovers" --source mangadex --chapter 5 --out ./downloads
.build/release/mangapy yaml samples/sample.yaml
```

`Sources/MangapyCLI` defines the command surface. `Sources/MangapyCore`
contains YAML validation, chapter selection, the provider clients, and archive
handling. SwiftPM resolves ArgumentParser, Yams, and SwiftSoup using
`Package.resolved`. Foundation handles networking, ImageIO validates JPEG, PNG,
GIF, WebP, BMP, and TIFF, and Core Graphics writes chapter PDFs.

The Swift CLI uses the Rust output layout. MangaDex keys a chapter by its
provider ID, which also works with `--chapter` to select a specific translation.
FanFox uses the normalized chapter number when available. Cached
images must decode successfully. PDFs are reused when their page count matches
the provider. When the feed supplies a page count, a warm PDF run needs only
manga and chapter metadata. Downloads serialize writes to each manga with a
file lock and keep validated temporary pages for resuming a failed PDF run.

```sh
swift test --disable-automatic-resolution
MANGAPY_LIVE_TESTS=1 swift test --disable-automatic-resolution --no-parallel --filter Live
```

Offline tests use synthesized HTML, JSON, and images. Live tests contact FanFox
and MangaDex to check catalog search and chapter page discovery. Download
availability and provider responses can change.
