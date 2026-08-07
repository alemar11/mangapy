## Development

## Configure VSCode

Install the Ruff VS Code extension and configure it as the Python formatter and
import organizer:

```json
{
    "ruff.nativeServer": "on",
    "[python]": {
        "editor.defaultFormatter": "charliermarsh.ruff",
        "editor.formatOnSave": true,
        "editor.codeActionsOnSave": {
            "source.fixAll.ruff": "explicit",
            "source.organizeImports.ruff": "explicit"
        }
    },
    "files.exclude": {
        "**/__pycache__": true,
        "**/*.egg-info": true,
        "**/dist": true,
        "**/build": true
    }
}
```

The repository configuration keeps the existing 130-character line length.

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
