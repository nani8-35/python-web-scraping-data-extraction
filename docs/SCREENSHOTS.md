# Project screenshots

All four deliverables are 1100 × 800 PNGs captured with headless Chrome:

1. `artifacts/screenshots/01-report.png` — the actual combined HTML run report.
2. `artifacts/screenshots/02-architecture.png` — an architecture presentation view.
3. `artifacts/screenshots/03-dataset.png` — a table loaded from the real books sample JSON.
4. `artifacts/screenshots/04-code.png` — actual repository paths and a source-code excerpt.

From the project root, with the installed environment active:

```bash
python scripts/build_sample_report.py
python docs/generate_screenshots.py
```

If an obsolete ChromeDriver on PATH conflicts with Chrome, prefix the second command with `SE_SKIP_DRIVER_IN_PATH=true`. The generator uses the project's Selenium dependencies, embedded styles and system fonts; Pillow is not required. It sets an exact 1100 × 800 browser viewport with device scale factor 1 and waits for fonts before capture.

The generator creates temporary presentation HTML for the architecture, dataset, and code views, then removes it after capture. The report image comes directly from `artifacts/report.html`. Changing sample records or source code changes the resulting images when regenerated.

For manual capture, open the report or generated view in Chrome, set a responsive viewport of 1100 × 800 at device scale 1, and capture the viewport using developer tools. Avoid browser chrome, cropping content, or changing metric values for appearance.
