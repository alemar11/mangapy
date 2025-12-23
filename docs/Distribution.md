## Generating distribution packages:

1. Make sure you have the latest version of **build** installed:  

```
python3 -m pip install --upgrade build
```

2. Now run this command from the project root:  

```
python3 -m build
```

## Uploading the distribution archives:

1. You can use **Twine** to upload the distribution packages. You’ll need to install Twine:  

```
python3 -m pip install --upgrade twine
```

2. Run **Twine** to upload all of the archives under dist:  

```
python3 -m twine upload dist/*
```
