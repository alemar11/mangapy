# mangapy

`mangapy` is a Rust CLI that downloads chapters as images or PDFs from FanFox
and MangaDex.

- CLI arguments live in `src/main.rs` and YAML configuration in `src/config.rs`.
- Request orchestration lives in `src/download.rs`. The CLI and benchmark
  share chapter selection and ordering in `src/selection.rs`.
- The provider interface, HTTP client, and MangaDex live in `src/provider.rs`.
- FanFox HTML parsing and packed JavaScript decoding live in `src/provider/fanfox.rs`.
  Preserve the unpacker unless a replacement handles the same input.
- Output paths, image validation, and PDF generation live in `src/archive.rs`.

Preserve CLI defaults, existing YAML files, finite decimal chapter numbers, and
idempotent output paths. Keep downloaded files under the configured output
directory and support home directory expansion. Register new sources in
`Source` and its provider factory.

Run `cargo test --locked` locally. Any new provider needs opt-in live tests
named `test_fetch_manga` and `test_fetch_manga_chapter_pages`; prefix other
provider-specific tests with the provider name. Live tests can fail when
providers are unavailable. Run a sample with
`cargo run --locked -- yaml samples/sample.yaml`.
