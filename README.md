# mangapy

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
pipenv install -e .
```

Run tests:

```
pipenv run pytest
```


TODO:

- logging
- https://stackoverflow.com/questions/14058453/making-python-loggers-output-all-messages-to-stdout-in-addition-to-log-file
- limit number of concurrent tasks
- config file
- test this case from cli: -c 1-4