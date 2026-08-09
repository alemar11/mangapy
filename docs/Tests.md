## Tests

Tests that contact FanFox or MangaDex are marked `live`. The default pytest
configuration excludes them, so the normal local command is deterministic and
does not require network access:

```
uv run pytest -q
```

Run the live provider suite explicitly:

```
uv run pytest -q -m live
```

Run every test, including the live provider suite, by overriding the default
`addopts` configuration:

```
uv run pytest -q -o addopts=""
```

Run one test file and stop after the first failure (`-x`). A live test file
still requires the explicit marker selection because the default is offline:

```
uv run pytest tests/test_fanfox.py -m live -x
```

## Linting and formatting

Run Ruff lint checks:

```
uv run ruff check .
```

Check formatting:

```
uv run ruff format --check .
```

Apply formatting locally:

```
uv run ruff format .
```
