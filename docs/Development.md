## Development

## Configure VSCode

settings.json

```json
{
    "python.linting.enabled": true,
    "python.linting.pylintEnabled": false,
    "python.linting.flake8Enabled": true,
    "python.linting.flake8Args": [
        "--max-line-length=130",
    ],
    "files.exclude": {
        "**/__pycache__": true,
        "**/*.egg-info": true,
        "**/dist": true,
        "**/build": true
    }
}
```

For users that want to set a default interpreter for a workspace, you can use the new setting `python.defaultInterpreterPath`.
With uv, the virtual environment is typically `.venv` in the project root, so you can set:
`"python.defaultInterpreterPath": "<repo>/.venv/bin/python"`.


## Installation

Sync the environment:

```
uv sync
```

By default, uv includes the `dev` dependency group; use `uv sync --no-dev` to exclude it.

Run commands inside the environment:

```
uv run python -m pytest
```

Recreate the virtual env:

```
rm -rf .venv
uv sync
```
