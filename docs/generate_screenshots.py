"""Capture the report and source-backed project views in headless Chrome."""

import json
import tempfile
from html import escape
from pathlib import Path

from scraping_system.config import Settings
from scraping_system.selenium.quotes_scraper import create_driver

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "artifacts/screenshots"
CSS = """
*{box-sizing:border-box}body{margin:0;background:#f3f6fa;color:#152b49;
font:16px -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}
main{padding:42px 48px;width:1100px;height:800px;overflow:hidden}
.eyebrow{font-size:12px;font-weight:700;letter-spacing:2px;color:#2563eb;text-transform:uppercase}
h1{font-size:34px;letter-spacing:-1px;margin:12px 0}h2{font-size:21px;margin:0 0 16px}
p{color:#607089;line-height:1.6}header{margin-bottom:30px}.muted{color:#69809e;font-size:13px}
.card{background:white;border:1px solid #dce4ee;border-radius:16px;padding:26px;
box-shadow:0 8px 24px #16365a06}.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:22px}
.grid .step{padding:12px;margin:12px 0}
.grid p{font-size:15px;line-height:1.45;margin:12px 0}
.grid .card{height:526px}
.step{border-left:3px solid #2563eb;padding:14px 16px;margin:16px 0;background:#f5f8fe}
.label{color:#2563eb;font-size:12px;letter-spacing:1px;font-weight:700}
.arrow{font-size:24px;color:#93a8c1;line-height:1}.pill{display:inline-block;padding:6px 10px;
background:#eff6ff;color:#245bb0;border-radius:6px;margin:4px 3px 0 0;font-size:13px}
footer{position:absolute;bottom:30px;left:48px;right:48px;border-top:1px solid #dce4ee;
padding-top:18px;display:flex;justify-content:space-between;color:#73859d;font-size:12px}
table{width:100%;border-collapse:collapse;font-size:14px}th{text-align:left;color:#6d7e94;
font-size:11px;text-transform:uppercase;letter-spacing:1px;padding:14px 10px;background:#f5f8fc}
td{padding:14px 10px;border-bottom:1px solid #edf1f6;line-height:1.35}
td:first-child{width:34%;font-weight:600}
.green{color:#16845c}.code{background:#101d32;color:#dce9fc;border-color:#243650}
pre{font:14px/1.65 ui-monospace,SFMono-Regular,Consolas,monospace;margin:0;white-space:pre-wrap}
.code-layout{display:grid;grid-template-columns:240px 1fr;gap:20px}
.tree{font-size:15px;line-height:2}
"""


def view(title: str, subtitle: str, body: str, name: str, directory: Path) -> Path:
    path = directory / f"{name}.html"
    path.write_text(
        '<!doctype html><html lang="en"><meta charset="utf-8">'
        f"<title>{escape(title)}</title><style>{CSS}</style><main><header>"
        '<div class="eyebrow">Python Web Scraping &amp; Data Extraction System</div>'
        f"<h1>{escape(title)}</h1><p>{escape(subtitle)}</p></header>{body}"
        "<footer><span>Independent engineering project · Public demo sources only</span>"
        "<span>Python / Scrapy / Selenium / PostgreSQL</span></footer></main></html>",
        encoding="utf-8",
    )
    return path


def build_views(directory: Path) -> dict[str, Path]:
    arch_body = (
        '<div class="grid"><section class="card"><h2>01 · Acquire</h2>'
        '<div class="label">APPROVED WEB SOURCES</div>'
        '<div class="step"><b>Books to Scrape</b><p>Static catalogue and product pages</p>'
        '<span class="pill">Scrapy</span></div><div class="muted">Independent sources</div>'
        '<div class="step"><b>Quotes to Scrape / JS</b><p>Browser-rendered quote pages</p>'
        '<span class="pill">Selenium</span><span class="pill">BeautifulSoup</span></div>'
        '<p class="muted">Bounded pagination · Polite delays<br>'
        "Retries · Browser cleanup</p></section>"
        '<section class="card"><h2>02 · Process</h2><div class="label">SHARED RECORD CONTRACT</div>'
        '<div class="step"><b>Normalize</b>'
        "<p>Whitespace, URLs, Decimal prices, currency, ratings</p></div>"
        '<div class="arrow">↓</div><div class="step"><b>Validate</b>'
        "<p>Pydantic models + rejection reasons</p></div>"
        '<div class="arrow">↓</div><div class="step"><b>Deduplicate</b>'
        "<p>Stable SHA-256 record identities</p></div>"
        '</section><section class="card"><h2>03 · Deliver</h2>'
        '<div class="label">STRUCTURED OUTPUTS</div>'
        '<div class="step"><b>CSV / JSON</b>'
        "<p>Predictable columns and portable serialized records</p></div>"
        '<div class="step"><b>PostgreSQL</b><p>Transactional upserts and run history</p></div>'
        '<div class="step"><b>HTML run report</b>'
        "<p>Actual counts, status, errors, and sample data</p></div>"
        "</section></div>"
    )
    architecture = view(
        "Two scraping engines. One accountable pipeline.",
        "Shared data contracts connect extraction, data quality, persistence, and reporting.",
        arch_body,
        "02-architecture",
        directory,
    )
    books = json.loads((ROOT / "sample_output/books_sample.json").read_text(encoding="utf-8"))
    rows = "".join(
        "<tr>"
        + "".join(
            f"<td>{escape(str(record[key]))}</td>"
            for key in ("title", "price", "currency", "availability", "rating", "category")
        )
        + "</tr>"
        for record in books[:7]
    )
    dataset_subtitle = (
        f"{len(books)} validated book records · Live source: books.toscrape.com · Seven-row preview"
    )
    dataset = view(
        "Real catalogue data, ready to use.",
        dataset_subtitle,
        '<section class="card"><div class="label">SAMPLE_OUTPUT / BOOKS_SAMPLE.CSV</div>'
        "<p>Exact decimal prices · Normalized ratings · Categories from product details</p>"
        "<table><thead><tr><th>Title</th><th>Price</th><th>Currency</th><th>Availability</th>"
        f"<th>Rating</th><th>Category</th></tr></thead><tbody>{rows}</tbody></table></section>",
        "03-dataset",
        directory,
    )
    source = (ROOT / "src/scraping_system/models/__init__.py").read_text(encoding="utf-8")
    snippet = source[
        source.index("class BookRecord") : source.index('    @field_validator("product_url")')
    ].strip()
    tree_lines = [
        "src/scraping_system/",
        "  cli.py",
        "  config.py",
        "  models/",
        "  spiders/",
        "  selenium/",
        "  pipelines/",
        "  exporters/",
        "  database/",
        "  reporting/",
        "  utils/",
        "tests/",
        "Dockerfile",
        "docker-compose.yml",
    ]
    tree = "\n".join(tree_lines)
    code_sub = (
        "Actual source excerpt: BookRecord schema and text validation · "
        "src/scraping_system/models/__init__.py"
    )
    code = view(
        "Typed contracts. Focused components.",
        code_sub,
        '<div class="code-layout"><aside class="card"><div class="label">REPOSITORY</div>'
        f'<pre class="tree">{escape(tree)}</pre></aside><section class="card code">'
        f"<pre>{escape(snippet)}</pre></section></div>",
        "04-code",
        directory,
    )
    return {
        "01-report": ROOT / "artifacts/report.html",
        "02-architecture": architecture,
        "03-dataset": dataset,
        "04-code": code,
    }


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="scraping-project-") as temp_dir:
        pages = build_views(Path(temp_dir))
        driver = create_driver(Settings(headless=True))
        try:
            driver.execute_cdp_cmd(
                "Emulation.setDeviceMetricsOverride",
                {
                    "width": 1100,
                    "height": 800,
                    "deviceScaleFactor": 1,
                    "mobile": False,
                },
            )
            for name, page in pages.items():
                driver.get(page.resolve().as_uri())
                driver.execute_async_script("document.fonts.ready.then(arguments[0]);")
                if not driver.save_screenshot(str(OUTPUT / f"{name}.png")):
                    raise RuntimeError(f"Screenshot failed: {name}")
                print(f"Captured {name}.png (1100 × 800)")
        finally:
            driver.quit()


if __name__ == "__main__":
    main()
