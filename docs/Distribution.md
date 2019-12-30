## Generating distribution packages:

1. Make sure you have the latest versions of **setuptools** and **wheel** installed:  

```
python3 -m pip install --user --upgrade setuptools wheel
```

2. Now run this command from the same directory where setup.py is located:  

```
python3 setup.py sdist bdist_wheel
```

## Uploading the distribution archives:

1. You can use **Twine** to upload the distribution packages. You’ll need to install Twine:  

```
python3 -m pip install --user --upgrade twine
```

2. Run **Twine** to upload all of the archives under dist:  

```
python3 -m twine upload --repository-url https://upload.pypi.org/legacy/ dist/*
```