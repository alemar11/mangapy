## Development

Install from local folder  

```
pip install .
```

Install from local folder (editable mode)  

```
pip install -e .
```

Install a local setup.py into your virtual environment/Pipfile:  

```
pipenv install --dev -e .
```

Recreate the virtual env:

```
pipenv shell
pipenv --rm
pipenv install -e .
```