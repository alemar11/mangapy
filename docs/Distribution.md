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
uv run --locked pytest -q \
  tests/test_cli.py \
  tests/test_providers.py \
  tests/test_download_manager.py \
  tests/test_chapter_archiver.py \
  tests/test_thread_safety.py \
  tests/test_fanfox_search.py \
  tests/test_fanfox_packed_js.py \
  tests/test_sort_key.py
```

4. Merge the release commit to `master`.
5. Tag the release with the package version, without a `v` prefix:

```
git tag 3.0.2
git push origin 3.0.2
```

The release workflow validates that the tag matches `pyproject.toml`, builds
the package, publishes it to PyPI with Trusted Publishing, and updates
`Formula/mangapy.rb` in `alemar11/homebrew-tap`.

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
matching GitHub tag archive:

```
brew update-python-resources --exclude-packages pillow --package-name mangapy --version 3.0.2 Formula/mangapy.rb
brew audit --strict --online mangapy
brew install --build-from-source mangapy
brew test mangapy
```

## Required GitHub/PyPI setup

- Configure PyPI Trusted Publishing for `alemar11/mangapy` and
  `.github/workflows/release.yml`.
- Add a `HOMEBREW_TAP_TOKEN` repository secret with write access to
  `alemar11/homebrew-tap`.
