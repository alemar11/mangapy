# Distribution

GitHub Releases distributes standalone Rust executables for macOS and Linux
on ARM64 and x86-64, and Windows on x86-64. PyPI wheels contain the same
executables. Homebrew builds from the tagged source with Cargo.

## Release flow

1. Bump the version in `Cargo.toml`, run `cargo check` to update `Cargo.lock`,
   then run `cargo test --locked`.
2. Merge the version bump to `main`.
3. Tag the merged commit with a stable `vX.Y.Z` and push that tag.

The workflow verifies the tag and its commit on `main`, tests and builds the
release matrix, and creates `release/vX.Y.Z` at the tagged commit. It publishes
the wheels and source distribution to PyPI using Trusted Publishing, uploads
the native archives to GitHub Releases, and opens or updates the Homebrew
formula PR in `alemar11/homebrew-tap`. Tap CI handles bottle publishing.

To retry publishing with the same built artifacts, rerun failed jobs. To rebuild
from the tagged commit, dispatch **Publish tagged release** from
`main` with the existing tag. Keep the PyPI Trusted Publisher configured for
`.github/workflows/release.yml` and the repository secret `HOMEBREW_TAP_TOKEN`
configured with write access to the tap.

## Local packaging

```console
cargo build --release --locked
uvx maturin build --release --locked --out dist
uvx maturin sdist --out dist
```

On Linux, use `maturin[zig]` with `--zig --compatibility manylinux_2_28` for a
portable wheel. The standalone binary needs no Python runtime.
