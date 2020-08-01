## Development

## Configure VSCode

settings.json

```json
{
    "python.pythonPath": "/Users/amarzoli/.local/share/virtualenvs/manga-S-NqUtI-/bin/python",
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

To configure pythonPath when using pipenv run: `pipenv --venv`


## Installation

Install from local folder  

```
pip install .
```

Install from local folder (editable mode)  

```
pip install -e .
```

Recreate the virtual env:

```
pipenv shell
pipenv --rm
pipenv install -e .
```