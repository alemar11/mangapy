## Distribution

`mangapy` is distributed through PyPI for `pipx` users and through the
`alemar11/homebrew-tap` Homebrew tap for Brew users.

## Release flow

1. Bump the package version in `pyproject.toml`.
2. Update and verify the lockfile:

```
uv lock
uv lock --check
```

3. Run the offline preflight tests:

```
uv run --locked pytest -q -m "not live"
```

4. Merge the release commit to `master`.
5. Tag the release with the package version, without a `v` prefix:

```
release_version="X.Y.Z"
git tag "${release_version}"
git push origin "${release_version}"
```

The release workflow validates that the tag matches `pyproject.toml`, builds
the package, publishes it to PyPI with Trusted Publishing, updates the
Homebrew formula URL and checksum, attempts to refresh Python resources, and
then validates the formula. The resource refresh explicitly bypasses
Homebrew's cooldown for newly uploaded main-package files, retries transient
PyPI propagation failures, and stops the release rather than publishing stale
dependency resources if every attempt fails.

## Manual build and publish

If CI publishing is unavailable, build and publish PyPI artifacts manually:

```
uv build
uv publish
```

Or, using a token:

```
UV_PUBLISH_TOKEN=... uv publish
```

Then update the Homebrew formula in `alemar11/homebrew-tap` to point at the
matching GitHub tag archive and refresh resources if dependency pins changed:

```
release_version="X.Y.Z"
archive_path="/tmp/mangapy-${release_version}.tar.gz"
curl --fail --location "https://github.com/alemar11/mangapy/archive/refs/tags/${release_version}.tar.gz" --output "${archive_path}"
shasum -a 256 "${archive_path}"
brew update-python-resources --ignore-main-package-cooldown --exclude-packages pillow --package-name mangapy --version "${release_version}" Formula/mangapy.rb
brew audit --strict --online mangapy
brew install --build-from-source mangapy
brew test mangapy
```

## Required GitHub/PyPI setup

- Configure PyPI Trusted Publishing for `alemar11/mangapy` and
  `.github/workflows/release.yml`.
- Add a `HOMEBREW_TAP_TOKEN` repository secret with write access to
  `alemar11/homebrew-tap`.
