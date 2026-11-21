# Development tools

## Browser inspection

The local web UI is inspected with the Playwright CLI. Install it once:

```bash
npm install -g --prefix ~/.local @playwright/cli@latest
playwright-cli install-browser chromium
```

Start the editor with `uv run photo-composition-designer` (default
`http://127.0.0.1:8767/`) and validate changes from cheapest to most realistic:

- **HTTP with curl:** `curl -sS -o /dev/null -w '%{http_code} %{redirect_url}\n' <url>`
  for status and redirects; use `-d`/`-X POST` when reproducing form submissions.
- **FastAPI TestClient:** `uv run pytest tests/test_gui.py -k <pattern> -x` for
  in-process endpoint and template checks, without starting a server or browser.
- **Chromium via Playwright CLI:** `playwright-cli open <url>`, then `find <text>`,
  `snapshot`, `click`, `fill`, `console`, `requests` and `screenshot`; close with
  `playwright-cli close`. Headless by default, `--headed` for visual checks.
- **Firefox:** install the browser once with
  `playwright-cli install-browser firefox`, then use
  `playwright-cli open --browser firefox <url>`.

Close browser sessions and stop the GUI when done. Transient Playwright output
goes to the ignored `.playwright-cli/` directory.

## Automated browser tests

`tests/test_browser_workflow.py` drives the critical editor flows against a real
uvicorn server in Chromium and Firefox. Install the Python package and the
browser binaries once:

```bash
uv run playwright install chromium firefox
uv run pytest tests/test_browser_workflow.py -m browser
```

The module skips when Playwright or the browser binaries are missing, so the
default `make test` run stays fast and portable. CI runs the suite only when the
browsers are installed.

## Release builds

Release artifacts are built from the current source tree:

```bash
make build-linux   # dist/photo-composition-designer + release/
make build-win     # dist/photo-composition-designer.exe + release/ (Windows)
make installer-win # dist/photo-composition-designer-setup.exe (requires iscc)
make check-release # verify the release/ contents
```

`build-linux` and `build-win` both run `make check-release`, which requires the
executable (with or without `.exe`), the three INI files, `README.md` and the
`res/`, `docs/` and `images/` directories. The PyInstaller data separator is
selected from `OS`: `;` on Windows and `:` elsewhere.

`installer-win` builds the per-user Inno Setup installer from
`installer/windows-installer.iss` into `dist/`. Install Inno Setup and put
`iscc` on `PATH` before running it.

The `release.yml` workflow runs Linux and Windows quality checks, builds both
archives and, on `windows-latest`, prepares Inno Setup through Chocolatey
before building the installer. It uploads the Windows ZIP and
`photo-composition-designer-setup.exe` to the GitHub release.

To verify a downloaded installer locally with Wine:

```bash
export WINEPREFIX=/tmp/opencode/wine-pcd
export WINEDEBUG=-all
rm -rf "$WINEPREFIX"
mkdir -p "$WINEPREFIX"
wine photo-composition-designer-setup.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /NOCANCEL /DIR=C:\PCD-Test
wine "$WINEPREFIX/drive_c/PCD-Test/photo-composition-designer.exe" gui --port 8794 --open-browser
curl -sS http://127.0.0.1:8794/health
curl -sS -X POST http://127.0.0.1:8794/shutdown
wine "$WINEPREFIX/drive_c/PCD-Test/unins000.exe" /VERYSILENT /NORESTART
```
