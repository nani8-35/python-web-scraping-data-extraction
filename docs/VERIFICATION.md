# Verification record

Executed locally on 2026-09-21 using Python 3.13 on macOS. These results describe the checked-in implementation; they are not throughput benchmarks or claims about client results.

## Automated checks

- `python -m pip install -e '.[dev]'` — succeeded; project dependencies installed.
- `python -m pip install . --no-deps` — wheel build and installation succeeded.
- `python -m pip check` — no broken dependencies.
- `ruff check .` and `ruff format --check .` — passed.
- `pytest -q` — **58 passed**, using fixtures and mocked browsers; no live-site requests in the unit suite.
- CLI help, invalid arguments, failed-run artifacts, exporter output, parser callbacks, and settings precedence were verified.

The host repeatedly applied a macOS hidden flag to the editable `.pth` file, which Python 3.13 skips. A normal wheel installation avoided this local environment issue. Development tests explicitly use `src/`. If your environment has the same issue, reinstall with `python -m pip install .`; an ordinary editable install works when its `.pth` file is not hidden.

## Live scrapers and exports

| Check | Observed result |
|---|---|
| Books → JSON, 2 pages, max 25 items | 25 accepted, 0 invalid, 0 duplicates |
| Same validated books → CSV | 25 rows, fields matched JSON |
| Books CLI → CSV, 2 pages, max 22 items | 22 accepted, report generated |
| Quotes JS → JSON, 2 pages | 20 accepted, 0 invalid, 0 duplicates |
| Combined `all` → JSON, 1 page and max 2 items per source | 2 books + 2 quotes, separate outputs, combined report |
| Books CLI → PostgreSQL, 1 page, max 3 items | 3 accepted, records and final run persisted |
| Final Selenium check with normal browser sandbox | 3 accepted, successful cleanup |

The full catalogue was not crawled; bounded live tests covered pagination and detail requests. The matching Selenium driver was selected using `SE_SKIP_DRIVER_IN_PATH=true` because the host had an obsolete driver on PATH. It was not deleted or replaced.

## PostgreSQL

Docker was unavailable. A separate temporary native PostgreSQL 14 cluster, with TCP listening disabled and a private Unix socket, was used instead of an existing database.

`scripts/verify_postgres.py` passed schema creation, book/quote persistence, exact Decimal roundtrip, successful run snapshots, and idempotent record/run upserts. Two exports of the same samples produced **25 books, 20 quotes, and 2 run rows**, with no duplicate growth. Evidence: [postgres_verification.json](../artifacts/postgres_verification.json). The temporary server was stopped after testing.

## Report and project images

The combined [report](../artifacts/report.html) is generated from the saved live runs in `sample_output/`: 45 accepted records and 4 processed pages. Its 36.12 seconds is the sum of those two recorded run durations, not a speed benchmark.

Four PNGs were captured through Chrome at exactly 1100 × 800 and visually inspected. The report capture shows the actual HTML dashboard. Architecture, dataset, and code views are produced by [generate_screenshots.py](generate_screenshots.py); data and code are read from the repository rather than copied into drawing commands.

## Remaining environment-dependent checks

- Docker image build, containerized browser execution, and `docker compose up -d postgres` could not be executed because Docker is not installed. Configuration and matching README commands are provided; container runtime behavior remains unverified.
- GitHub Actions configuration is included but no remote repository or hosted CI run was created.
- Python 3.12 is the supported minimum; this local run used Python 3.13. The CI matrix includes both.
- Runs retain records in memory. Latest-run artifact paths are shared within a working directory, so concurrent invocations should use separate directories.
