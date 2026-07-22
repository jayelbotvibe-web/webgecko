# CLAUDE.md — webgecko

A Python web-scraping library for sites that block plain `curl`/`requests` but don't need
JavaScript. Combines curl_cffi TLS/browser impersonation, an lxml-backed parser with
CSS/XPath plus `::text` and `::attr()` pseudo-element shortcuts, markdown/links/JSON-LD
extraction aimed at AI agents, and a small concurrent crawler.

Deliberately excludes browser automation, JS rendering, proxy rotation, and CAPTCHA
solving — "a library, not a scraping framework."

**Distribution name is `webgecko`; import name is `gecko`.** `pip install webgecko`, then
`from gecko import fetch`.

## Commands

```bash
pip install -e ".[dev]"    # dev install
pytest -v                  # test (91 tests)
```

**There is no lint command anywhere** — no ruff/flake8/black config, no lint step in CI, no
Makefile. Do not invent one. No build script either; packaging is standard setuptools via
`pyproject.toml`.

## Stack

`pyproject.toml`: `requires-python = ">=3.10"`, `version = "0.1.0"`, setuptools backend.

```
lxml>=6.0
cssselect>=1.4
curl_cffi>=0.15
anyio>=4.0
```

Dev extras: `pytest`, `pytest-asyncio`, `pytest-httpbin` (unpinned).

**CI/metadata mismatch worth knowing:** `pyproject.toml` claims and classifies Python 3.10,
but CI tests only 3.11–3.13 (commit `b51fe5a`: "drop python 3.10 — dep wheel issue"). 3.10
is claimed as supported but is **not tested**.

## Architecture

No CLI, no executable entry point (no `[project.scripts]`). The public surface is
`gecko/__init__.py`, which exports `fetch`, `Session`, `AsyncSession`, `Response`, `Page`,
`Gecko`, `__version__`.

- `gecko/parser.py` (375 lines) — largest module: `Page`, `Elements`, navigation,
  pseudo-elements, `extract()`, `markdown`, `links()`, `jsonld()`, `title`
- `gecko/fetcher.py` (174 lines) — `fetch()`, `Session`, `AsyncSession`, `Response`, and
  the `_retry` helper wrapping curl_cffi
- `gecko/crawler.py` (156 lines) — the `Gecko` base class users subclass with
  `start_urls`/`parse()`; anyio task-group worker pool
- `tests/test_gecko.py` (588 lines) — the entire suite, 91 test functions

## Conventions

- Tests grouped into classes by subsystem (`class TestParser:`) in one file, with
  behavior-descriptive names (`test_pseudo_attr_on_none`, `test_find_all_class_underscore`)
- **Network tests use the local `pytest-httpbin` fixture, never live URLs** — deliberate,
  per commit `da6301f` "zero flaky tests". Keep it that way; don't add a test that hits the
  internet.
- Keyword-only arguments after `*` in the public API
- Type hints on public signatures
- Private helpers prefixed `_`
- Conventional Commits, mostly

## Gotchas

- **No env vars, config files, credentials, or external services.** Tests run fully offline.
- Hardcoded defaults that surprise people: `impersonate="chrome131"`, `timeout=30`,
  `retries=3`, `retry_delay=1.0`, crawler `concurrency=4`. Retries fire on **connection
  errors only**.
- `curl_cffi` ships compiled wheels — that's the dependency behind the dropped-3.10 CI issue.
- The README's first example hits the live network (`https://httpbin.org/html`); the tests
  do not. Don't copy that pattern into a test.
- **`r.page` is a placeholder for non-HTML (JSON) responses** — a real trap when handling
  mixed content types.
- Whether the package is actually published to PyPI is **unknown** from the repo alone,
  despite the README badges.

## State

Complete and coherent for `0.1.0` / "Development Status :: 3 - Alpha". Well-tested: 91
tests for ~700 lines of source. Zero TODO/FIXME. CI runs on push/PR to `master` or `main`.
Recent commits are docs and CI polish rather than features — it has settled. Clean tree on
`master` (default branch), synced.
