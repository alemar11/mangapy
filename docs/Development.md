# Development

Install stable Rust with `rustup` or `mise install`. Run the executable from the
checkout with `cargo run --locked -- title "Backstage Lovers" -s mangadex` or
`cargo run --locked -- yaml samples/sample.yaml`.

- `src/main.rs` handles CLI arguments. `src/config.rs` resolves YAML and
  output defaults into a typed request.
- `src/download.rs` plans and executes requests. `src/selection.rs` is shared
  with the benchmark.
- `src/provider.rs` defines the provider interface, shared HTTP behavior, and MangaDex.
- `src/provider/fanfox.rs` handles FanFox HTML and packed scripts.
- `src/archive.rs` handles output paths, image validation, and PDF creation.

Use rust-analyzer in VS Code. Run `cargo fmt` before submitting changes.

The native benchmark writes elapsed milliseconds as JSON. Use `--pages`,
`--images`, `--pdf`, or `--pdf-only` to select phases, and `--rounds` to
repeat a measurement. Pass `--out` to choose where it stores downloads.

```console
cargo run --release --locked --example benchmark -- -s mangadex -t "Backstage Lovers" --pages
```
