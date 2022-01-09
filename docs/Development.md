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
i.e. `"python.defaultInterpreterPath": "/Users/amarzoli/.local/share/virtualenvs/mangapy-SS8vXwx4/bin/python"`

To configure `defaultInterpreterPath` when using pipenv run: `pipenv --venv`


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