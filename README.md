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
- store all the images inside a MangaName/images directory so that we can have a MangaName/pdf directory
- config file
- referer, keep alive is required?
