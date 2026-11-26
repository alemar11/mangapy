# Tests

Run `cargo test --locked` for the offline suite. Use `cargo test --locked -- test_name`
to run tests matching a name.

Run provider tests with `cargo test --locked -- --ignored --test-threads=1`.
They contact FanFox and MangaDex and can fail when the provider is unavailable
or changes its catalog. The CI schedule runs these separately.

To verify the packaged CLI locally, build with `cargo build --release --locked`
and run `target/release/mangapy --version`.
