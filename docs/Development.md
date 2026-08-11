## Development

## Configure VS Code

Open the repository in VS Code and accept its recommended Python, Python
Environments, Python Debugger, and Ruff extensions. VS Code automatically
discovers and prioritizes the workspace-local `.venv`; the tracked settings
enable pytest discovery and configure Ruff for formatting, safe fixes, and
import organization on save. Ruff reads its lint and formatting rules from
`pyproject.toml`, including the 130-character line length.

The repository's `mise.toml` selects Python 3.14 and uv. Run `mise install` and
`mise run setup` before opening VS Code. The `.venv` interpreter remains the
correct VS Code selection: uv creates it from mise's Python while keeping the
project dependencies isolated.

After running `uv sync`, tests appear in Test Explorer. They can be run or
debugged individually there. The Run and Debug view also provides configurations
for the current Python file, the MangaPy CLI, the complete offline test suite,
and a selected test. The CLI configuration uses `--version` by default; replace
its `args` in `.vscode/launch.json` when debugging a download.

## Installation

Sync the environment:

```
mise install
mise run setup
```

By default, uv includes the `dev` dependency group; use `uv sync --no-dev` to exclude it.

Run the deterministic, offline test suite inside the environment (this is the
default pytest selection):

```
mise run test
```

See [Tests.md](Tests.md) for the live-provider and complete-suite commands.

Recreate the virtual env:

```
rm -rf .venv
uv sync
```
