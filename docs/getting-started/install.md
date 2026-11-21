# Installation

## PyPI

### Install or update the package from PyPI

Download from [PyPI](https://pypi.org/):

```bash
pip install --upgrade Photo-Composition-Designer
```

The same command updates an existing installation.

### Isolated installs

Keep the app in its own environment with pipx:

```bash
pipx install --force Photo-Composition-Designer
```

This installs the latest release or replaces an existing pipx installation.
Alternatively, use uv:

```bash
uv tool install --upgrade Photo-Composition-Designer
```

If uv reports that the executable directory is not on `PATH`, run
`uv tool update-shell` once and restart the terminal.

### Start the local web editor

```bash
photo-composition-designer
```

Then open `http://127.0.0.1:8767/`. The explicit `gui` command is equivalent.
The editor is the primary interface; the command line covers scanning,
distribution, rendering, export, duplication and diagnostics. See the
[web UI guide](../usage/web-ui.md) and the [CLI reference](../usage/cli.md).

## Executable

### Windows installer (recommended)

Download the installer from the
[latest release](https://github.com/pamagister/Photo-Composition-Designer/releases/latest):

- [Download the Windows installer](https://github.com/pamagister/Photo-Composition-Designer/releases/latest/download/photo-composition-designer-setup.exe)

The installer is per-user by default and adds a Start Menu shortcut. The
shortcut runs `photo-composition-designer.exe gui --open-browser`: a console
window stays open while the server runs, and the browser opens on the project
page. Close the console window or use **Stop server** in the web UI to stop the
app. The installer also offers an optional desktop icon and includes an
uninstaller.

### Archives

- [Download the Windows ZIP](https://github.com/pamagister/Photo-Composition-Designer/releases/latest/download/photo-composition-designer-win.zip)
- [Download the Linux ZIP](https://github.com/pamagister/Photo-Composition-Designer/releases/latest/download/photo-composition-designer-linux.zip)

Unzip the archive and start the app from the extracted folder. On Windows, run
`photo-composition-designer.exe gui --open-browser` from a terminal to open the
browser automatically; double-clicking the executable starts the editor without
opening a browser. On Linux, run `./photo-composition-designer` from a terminal.

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
uv run photo-composition-designer
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
