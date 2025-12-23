## Generating distribution packages:

1. Build sdist and wheel with uv from the project root:

```
uv build
```

## Uploading the distribution archives:

1. Publish all files under `dist/` with uv (token via env var or flag):

```
uv publish
```

Or, using a token:

```
UV_PUBLISH_TOKEN=... uv publish
```
