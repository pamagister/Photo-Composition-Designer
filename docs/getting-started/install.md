# Installation

## PyPI

### Install the package from PyPI

Download from [PyPI](https://pypi.org/):

```bash
pip install Photo-Composition-Designer
```

### Start the local web editor

```bash
photo-composition-designer gui
```

Then open `http://127.0.0.1:8767/`. The editor is the primary interface; the
command line covers scanning, distribution, rendering, export, duplication and
diagnostics. See the [web UI guide](../usage/web-ui.md) and the
[CLI reference](../usage/cli.md).

## Executable

Download the latest executable:

- [Download for Windows](https://github.com/pamagister/Photo-Composition-Designer/releases/latest/download/photo-composition-designer-win.zip)
- [Download for Linux](https://github.com/pamagister/Photo-Composition-Designer/releases/latest/download/photo-composition-designer-linux.zip)
- [Download for macOS](https://github.com/pamagister/Photo-Composition-Designer/releases/latest/download/photo-composition-designer-macos.zip)

## Run from source

### Clone the repository

```bash
git clone https://github.com/pamagister/Photo-Composition-Designer
cd Photo-Composition-Designer
```

### Install dependencies

```bash
uv venv
uv pip install -e ".[dev,docs]"
```

### Start the editor from source

```bash
uv run photo-composition-designer gui
```

### Run the checks

```bash
make lint
make test
```

### Browser tests

The Playwright suite covers the critical editor flows in Chromium and Firefox. It
skips when Playwright or the browser binaries are unavailable:

```bash
uv run playwright install chromium firefox
uv run pytest tests/test_browser_workflow.py -m browser
```
