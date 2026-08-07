## Tests

Run tests:  

```
uv run pytest
```

Run tests defined in a specific test and stopping them once the first failure occurs (`-x`)

```
uv run pytest tests/test_fanfox.py -x
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
