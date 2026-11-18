# Development tools

## Browser inspection

The local web UI is inspected with the Playwright CLI. Install it once:

```bash
npm install -g --prefix ~/.local @playwright/cli@latest
playwright-cli install-browser chromium
```

Start the editor with `uv run photo-composition-designer gui` (default
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
