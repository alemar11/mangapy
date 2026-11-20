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

4. Merge the version bump to `main`.
5. Tag the merged commit and push the tag:

```bash
release_version="X.Y.Z"
release_commit="<SHA of the merged version bump>"
git tag -a "v${release_version}" "${release_commit}" -m "Release v${release_version}"
git push origin "refs/tags/v${release_version}"
```

The workflow checks that the tagged commit is on `main` and that the tag
matches `pyproject.toml`. After the offline tests and build pass, it creates
`release/vX.Y.Z` at the tagged commit, publishes to PyPI with Trusted
Publishing, and opens or updates the formula PR in the Homebrew tap.
The tap CI validates the formula and handles bottle publishing.

To retry, rerun the workflow or launch **Publish tagged release** from
`main` with the same tag. It reuses a release branch at the tagged commit
and skips the PyPI upload if both artifacts are already published. A release
branch pointing to a different commit stops the workflow.

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
curl --fail --location "https://github.com/alemar11/mangapy/archive/refs/tags/v${release_version}.tar.gz" --output "${archive_path}"
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
