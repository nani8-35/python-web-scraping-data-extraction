"""Render portable, escaped dashboards from final run metrics and typed records."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from html import escape
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from scraping_system.models import Record, RunMetrics


def _get_attr(obj: Any, key: str, default: Any = None) -> Any:
    """Safely get attribute or dict item from a metric or record."""
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _format_datetime(dt: Any) -> str:
    if isinstance(dt, datetime):
        return dt.strftime("%Y-%m-%d %H:%M:%S UTC")
    if dt:
        return str(dt)
    return "N/A"


def _format_elapsed(seconds: Any) -> str:
    try:
        val = float(seconds)
        if val < 0:
            return "0.00s"
        if val < 60:
            return f"{val:.2f}s"
        mins = int(val // 60)
        secs = val % 60
        return f"{mins}m {secs:.1f}s"
    except (TypeError, ValueError):
        return "N/A"


def _render_stars(rating: Any) -> str:
    try:
        r = int(rating)
        r = max(1, min(5, r))
    except (TypeError, ValueError):
        r = 0
    filled = "★" * r
    empty = "☆" * (5 - r)
    return (
        f'<span class="rating-stars" title="{r} of 5 stars">{filled}{empty}</span> '
        f'<span class="rating-num">({r}/5)</span>'
    )


def _record_to_dict(record: Any) -> dict[str, Any]:
    if hasattr(record, "model_dump"):
        return record.model_dump(mode="json")
    if isinstance(record, dict):
        return record
    if hasattr(record, "__dict__"):
        return dict(vars(record))
    return {}


def _render_book_row(data: dict[str, Any], idx: int) -> str:
    title = escape(str(data.get("title", "")))
    price = data.get("price", "0.00")
    currency = escape(str(data.get("currency", "GBP")))
    availability = escape(str(data.get("availability", "")))
    rating = data.get("rating", 0)
    category = escape(str(data.get("category", "")))
    product_url = escape(str(data.get("product_url", "")))
    scraped_at = escape(_format_datetime(data.get("scraped_at")))

    symbols = {"GBP": "£", "USD": "$", "EUR": "€"}
    sym = symbols.get(currency, currency)
    is_num = (
        isinstance(price, (int, float, Decimal, str)) and str(price).replace(".", "", 1).isdigit()
    )
    price_str = escape(f"{sym}{Decimal(str(price)):.2f}" if is_num else str(price))
    avail_class = "badge-success" if "in stock" in availability.lower() else "badge-warning"

    return f"""<tr>
  <td class="cell-num">{idx}</td>
  <td class="cell-title" title="{title}">{title}</td>
  <td class="cell-category"><span class="badge badge-secondary">{category}</span></td>
  <td class="cell-price">{price_str}</td>
  <td class="cell-rating">{_render_stars(rating)}</td>
  <td class="cell-avail"><span class="badge {avail_class}">{availability}</span></td>
  <td class="cell-url">
    <a href="{product_url}" target="_blank" rel="noopener noreferrer">View Product ↗</a>
  </td>
  <td class="cell-time">{scraped_at}</td>
</tr>"""


def _render_quote_row(data: dict[str, Any], idx: int) -> str:
    quote = escape(str(data.get("quote", "")))
    author = escape(str(data.get("author", "")))
    tags = data.get("tags", [])
    source_url = escape(str(data.get("source_url", "")))
    scraped_at = escape(_format_datetime(data.get("scraped_at")))

    if tags:
        tag_html = " ".join(f'<span class="tag-pill">{escape(str(t))}</span>' for t in tags)
    else:
        tag_html = '<span class="text-muted">None</span>'

    return f"""<tr>
  <td class="cell-num">{idx}</td>
  <td class="cell-quote">"{quote}"</td>
  <td class="cell-author"><strong>{author}</strong></td>
  <td class="cell-tags">{tag_html}</td>
  <td class="cell-url">
    <a href="{source_url}" target="_blank" rel="noopener noreferrer">View Source ↗</a>
  </td>
  <td class="cell-time">{scraped_at}</td>
</tr>"""


def generate_report(
    runs: list[RunMetrics] | list[Any],
    records: list[Record] | list[Any],
    destination: Path,
) -> Path:
    """Render a self-contained, responsive HTML run report dashboard.

    Parameters
    ----------
    runs : list[RunMetrics]
        Final execution metrics for one or more scraper runs.
    records : list[Record]
        List of extracted BookRecord, QuoteRecord, or compatible records.
    destination : Path
        Target path for the rendered HTML report.

    Returns
    -------
    Path
        The destination path of the generated report.
    """
    dest_path = Path(destination)
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    total_pages = sum(int(_get_attr(r, "pages_processed", 0)) for r in runs)
    total_extracted = sum(int(_get_attr(r, "extracted", 0)) for r in runs)
    total_accepted = sum(int(_get_attr(r, "accepted", 0)) for r in runs)
    total_invalid = sum(int(_get_attr(r, "invalid", 0)) for r in runs)
    total_duplicates = sum(int(_get_attr(r, "duplicates", 0)) for r in runs)
    total_retries = sum(int(_get_attr(r, "retries", 0)) for r in runs)
    total_elapsed = sum(float(_get_attr(r, "elapsed_seconds", 0.0) or 0.0) for r in runs)

    overall_status = "completed" if runs else "no runs"
    for r in runs:
        st = str(_get_attr(r, "status", "completed")).lower()
        if st in ("failed", "error", "interrupted"):
            overall_status = "failed"
            break
        if st in ("running", "partial") and overall_status != "failed":
            overall_status = st
        elif st == "success" and overall_status not in ("failed", "running", "partial"):
            overall_status = "success"

    generated_time = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")

    if overall_status in ("completed", "success"):
        status_badge_class = "badge-success"
    elif overall_status in ("failed", "interrupted"):
        status_badge_class = "badge-danger"
    else:
        status_badge_class = "badge-warning"

    run_rows = []
    all_errors = []
    for idx, r in enumerate(runs, 1):
        run_id = escape(str(_get_attr(r, "run_id", "N/A")))
        source = escape(str(_get_attr(r, "source", "N/A")))
        status = escape(str(_get_attr(r, "status", "unknown")))
        started = _format_datetime(_get_attr(r, "started_at"))
        pages = _get_attr(r, "pages_processed", 0)
        extracted = _get_attr(r, "extracted", 0)
        accepted = _get_attr(r, "accepted", 0)
        invalid = _get_attr(r, "invalid", 0)
        dups = _get_attr(r, "duplicates", 0)
        retries = _get_attr(r, "retries", 0)
        elapsed = _format_elapsed(_get_attr(r, "elapsed_seconds", 0.0))
        fmt = escape(str(_get_attr(r, "output_format", "json")).upper())
        out_path = escape(str(_get_attr(r, "output_path", "N/A")))
        errs = _get_attr(r, "errors", [])
        if errs:
            all_errors.extend(errs)

        st_lower = status.lower()
        if st_lower in ("completed", "success"):
            row_status_class = "badge-success"
        elif st_lower in ("failed", "interrupted"):
            row_status_class = "badge-danger"
        else:
            row_status_class = "badge-warning"

        run_rows.append(f"""<tr>
  <td class="cell-num">{idx}</td>
  <td><span class="mono-badge">{run_id[:8]}...</span></td>
  <td><strong>{source}</strong></td>
  <td><span class="badge {row_status_class}">{status}</span></td>
  <td class="cell-time">{started}</td>
  <td>{pages}</td>
  <td>{extracted}</td>
  <td class="text-success font-semibold">{accepted}</td>
  <td class="{"text-danger font-semibold" if invalid else ""}">{invalid}</td>
  <td>{dups}</td>
  <td>{retries}</td>
  <td>{elapsed}</td>
  <td><span class="badge badge-secondary">{fmt}</span></td>
  <td class="cell-path" title="{out_path}">{out_path}</td>
</tr>""")

    if run_rows:
        run_table_html = "\n".join(run_rows)
    else:
        run_table_html = (
            "<tr><td colspan='14' class='text-center text-muted'>No run metrics recorded</td></tr>"
        )

    book_dicts = []
    quote_dicts = []
    for rec in records:
        d = _record_to_dict(rec)
        if "quote" in d or "author" in d:
            quote_dicts.append(d)
        else:
            book_dicts.append(d)

    book_rows = [_render_book_row(b, i) for i, b in enumerate(book_dicts[:50], 1)]
    book_table_html = "\n".join(book_rows)

    quote_rows = [_render_quote_row(q, i) for i, q in enumerate(quote_dicts[:50], 1)]
    quote_table_html = "\n".join(quote_rows)

    books_section_html = ""
    if book_dicts:
        footer = ""
        if len(book_dicts) > len(book_rows):
            footer = (
                f'<div class="card-footer text-muted">'
                f"Showing first {len(book_rows)} of {len(book_dicts)} book records</div>"
            )
        books_section_html = f"""
<div class="card">
  <div class="card-header">
    <div class="card-title-group">
      <h3 class="card-title">Extracted Books Sample</h3>
      <span class="badge badge-primary">{len(book_dicts)} records</span>
    </div>
    <span class="card-subtitle">Source: books.toscrape.com (Static Scrapy Extraction)</span>
  </div>
  <div class="table-responsive">
    <table class="data-table">
      <thead>
        <tr>
          <th>#</th>
          <th>Title</th>
          <th>Category</th>
          <th>Price</th>
          <th>Rating</th>
          <th>Availability</th>
          <th>Product URL</th>
          <th>Scraped At</th>
        </tr>
      </thead>
      <tbody>
        {book_table_html}
      </tbody>
    </table>
  </div>
  {footer}
</div>
"""

    quotes_section_html = ""
    if quote_dicts:
        footer = ""
        if len(quote_dicts) > len(quote_rows):
            footer = (
                f'<div class="card-footer text-muted">'
                f"Showing first {len(quote_rows)} of {len(quote_dicts)} quote records</div>"
            )
        quotes_section_html = f"""
<div class="card">
  <div class="card-header">
    <div class="card-title-group">
      <h3 class="card-title">Extracted Quotes Sample</h3>
      <span class="badge badge-primary">{len(quote_dicts)} records</span>
    </div>
    <span class="card-subtitle">Source: quotes.toscrape.com/js/ (Selenium JS Extraction)</span>
  </div>
  <div class="table-responsive">
    <table class="data-table">
      <thead>
        <tr>
          <th>#</th>
          <th>Quote</th>
          <th>Author</th>
          <th>Tags</th>
          <th>Source URL</th>
          <th>Scraped At</th>
        </tr>
      </thead>
      <tbody>
        {quote_table_html}
      </tbody>
    </table>
  </div>
  {footer}
</div>
"""

    empty_records_html = ""
    if not book_dicts and not quote_dicts:
        empty_records_html = """
<div class="card empty-card">
  <div class="empty-icon">📂</div>
  <h3>No Records Extracted</h3>
  <p class="text-muted">
    This run completed without producing any accepted records.
    Check the run metrics or error logs above for details.
  </p>
</div>
"""

    error_box_html = ""
    if all_errors:
        err_items = "".join(f"<li>{escape(str(e))}</li>" for e in all_errors)
        error_box_html = f"""
<div class="alert alert-danger">
  <strong>Operational Warnings / Errors:</strong>
  <ul>{err_items}</ul>
</div>
"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Extraction Run Report — Python Web Scraping System</title>
  <style>
    :root {{
      --bg-canvas: #f8fafc;
      --bg-card: #ffffff;
      --border-color: #e2e8f0;
      --border-subtle: #cbd5e1;
      --text-main: #0f172a;
      --text-muted: #64748b;
      --primary-navy: #0f2744;
      --primary-blue: #2563eb;
      --primary-blue-light: #eff6ff;
      --success-green: #15803d;
      --success-bg: #f0fdf4;
      --warning-amber: #b45309;
      --warning-bg: #fffbeb;
      --danger-red: #b91c1c;
      --danger-bg: #fef2f2;
      --font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
      --font-mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    }}

    * {{
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }}

    body {{
      font-family: var(--font-family);
      background-color: var(--bg-canvas);
      color: var(--text-main);
      line-height: 1.5;
      padding: 2rem 1.5rem;
      -webkit-font-smoothing: antialiased;
    }}

    .container {{
      max-width: 1280px;
      margin: 0 auto;
    }}

    /* Header */
    .header {{
      background: var(--bg-card);
      border: 1px solid var(--border-color);
      border-radius: 12px;
      padding: 1.75rem 2rem;
      margin-bottom: 1.5rem;
      display: flex;
      justify-content: space-between;
      align-items: center;
      box-shadow: 0 1px 3px rgba(0,0,0,0.03);
    }}

    .header-left h1 {{
      font-size: 1.5rem;
      font-weight: 700;
      color: var(--primary-navy);
      letter-spacing: -0.02em;
      margin-bottom: 0.25rem;
    }}

    .header-left p {{
      color: var(--text-muted);
      font-size: 0.9rem;
    }}

    .header-right {{
      text-align: right;
      display: flex;
      flex-direction: column;
      align-items: flex-end;
      gap: 0.5rem;
    }}

    .header-meta {{
      font-size: 0.8rem;
      color: var(--text-muted);
    }}

    /* KPI Grid */
    .kpi-grid {{
      display: grid;
      grid-template-columns: repeat(6, minmax(0, 1fr));
      gap: 1rem;
      margin-bottom: 1.5rem;
    }}

    .kpi-card {{
      background: var(--bg-card);
      border: 1px solid var(--border-color);
      border-radius: 10px;
      padding: 1.25rem 1rem;
      box-shadow: 0 1px 2px rgba(0,0,0,0.02);
      transition: transform 0.15s ease;
    }}

    .kpi-card:hover {{
      transform: translateY(-2px);
      box-shadow: 0 4px 6px rgba(0,0,0,0.04);
    }}

    .kpi-label {{
      font-size: 0.75rem;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--text-muted);
      font-weight: 600;
      margin-bottom: 0.35rem;
    }}

    .kpi-value {{
      font-size: 1.75rem;
      font-weight: 700;
      color: var(--primary-navy);
      line-height: 1.1;
    }}

    .kpi-sub {{
      font-size: 0.75rem;
      color: var(--text-muted);
      margin-top: 0.35rem;
    }}

    /* Cards */
    .card {{
      background: var(--bg-card);
      border: 1px solid var(--border-color);
      border-radius: 12px;
      margin-bottom: 1.5rem;
      overflow: hidden;
      box-shadow: 0 1px 3px rgba(0,0,0,0.03);
    }}

    .card-header {{
      padding: 1.25rem 1.5rem;
      border-bottom: 1px solid var(--border-color);
      display: flex;
      justify-content: space-between;
      align-items: center;
      background-color: #fafbfd;
    }}

    .card-title-group {{
      display: flex;
      align-items: center;
      gap: 0.75rem;
    }}

    .card-title {{
      font-size: 1.1rem;
      font-weight: 600;
      color: var(--primary-navy);
    }}

    .card-subtitle {{
      font-size: 0.825rem;
      color: var(--text-muted);
    }}

    .card-footer {{
      padding: 0.75rem 1.5rem;
      background: #fafbfd;
      border-top: 1px solid var(--border-color);
      font-size: 0.8rem;
    }}

    /* Pipeline Flow */
    .flow-container {{
      padding: 1.5rem;
      display: flex;
      align-items: center;
      justify-content: space-between;
      flex-wrap: wrap;
      gap: 0.75rem;
      background: #ffffff;
    }}

    .flow-node {{
      flex: 1;
      min-width: 110px;
      background: var(--bg-canvas);
      border: 1px solid var(--border-color);
      border-radius: 8px;
      padding: 1rem 0.75rem;
      text-align: center;
      position: relative;
    }}

    .flow-step {{
      font-size: 0.65rem;
      font-weight: 700;
      color: var(--primary-blue);
      text-transform: uppercase;
      letter-spacing: 0.05em;
      margin-bottom: 0.2rem;
    }}

    .flow-name {{
      font-size: 0.9rem;
      font-weight: 600;
      color: var(--primary-navy);
      margin-bottom: 0.2rem;
    }}

    .flow-desc {{
      font-size: 0.725rem;
      color: var(--text-muted);
    }}

    .flow-arrow {{
      color: var(--primary-blue);
      font-size: 1.25rem;
      font-weight: bold;
      user-select: none;
    }}

    /* Tech Stack Badges */
    .stack-grid {{
      display: flex;
      flex-wrap: wrap;
      gap: 0.6rem;
      padding: 1.25rem 1.5rem;
    }}

    .tech-pill {{
      display: inline-flex;
      align-items: center;
      gap: 0.4rem;
      background: var(--primary-blue-light);
      color: var(--primary-blue);
      font-size: 0.8rem;
      font-weight: 600;
      padding: 0.4rem 0.85rem;
      border-radius: 9999px;
      border: 1px solid #bfdbfe;
    }}

    /* Tables */
    .table-responsive {{
      overflow-x: auto;
      max-height: 520px;
    }}

    .data-table {{
      width: 100%;
      border-collapse: collapse;
      text-align: left;
      font-size: 0.85rem;
    }}

    .data-table th {{
      background: #f1f5f9;
      color: var(--text-muted);
      font-weight: 600;
      font-size: 0.75rem;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      padding: 0.75rem 1rem;
      border-bottom: 1px solid var(--border-color);
      position: sticky;
      top: 0;
      z-index: 1;
    }}

    .data-table td {{
      padding: 0.75rem 1rem;
      border-bottom: 1px solid var(--border-color);
      color: var(--text-main);
      vertical-align: middle;
    }}

    .data-table tbody tr:hover {{
      background-color: #f8fafc;
    }}

    /* Specific cells */
    .cell-num {{
      color: var(--text-muted);
      font-size: 0.8rem;
      width: 40px;
    }}

    .cell-title {{
      font-weight: 500;
      max-width: 280px;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }}

    .cell-quote {{
      font-style: italic;
      max-width: 400px;
      white-space: normal;
      line-height: 1.4;
    }}

    .cell-author {{
      white-space: nowrap;
    }}

    .cell-price {{
      font-family: var(--font-mono);
      font-weight: 600;
      color: var(--primary-navy);
    }}

    .cell-url a {{
      color: var(--primary-blue);
      text-decoration: none;
      font-size: 0.8rem;
    }}

    .cell-url a:hover {{
      text-decoration: underline;
    }}

    .cell-time {{
      color: var(--text-muted);
      font-size: 0.75rem;
      white-space: nowrap;
    }}

    .cell-path {{
      font-family: var(--font-mono);
      font-size: 0.75rem;
      color: var(--text-muted);
      max-width: 200px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }}

    /* Badges */
    .badge {{
      display: inline-block;
      padding: 0.2rem 0.55rem;
      font-size: 0.725rem;
      font-weight: 600;
      border-radius: 4px;
      text-transform: capitalize;
    }}

    .badge-primary {{
      background: var(--primary-blue-light);
      color: var(--primary-blue);
      border: 1px solid #bfdbfe;
    }}

    .badge-secondary {{
      background: #f1f5f9;
      color: #475569;
      border: 1px solid var(--border-color);
    }}

    .badge-success {{
      background: var(--success-bg);
      color: var(--success-green);
      border: 1px solid #bbf7d0;
    }}

    .badge-warning {{
      background: var(--warning-bg);
      color: var(--warning-amber);
      border: 1px solid #fde68a;
    }}

    .badge-danger {{
      background: var(--danger-bg);
      color: var(--danger-red);
      border: 1px solid #fecaca;
    }}

    .mono-badge {{
      font-family: var(--font-mono);
      font-size: 0.75rem;
      background: #f1f5f9;
      padding: 0.15rem 0.4rem;
      border-radius: 4px;
      border: 1px solid var(--border-color);
    }}

    .tag-pill {{
      display: inline-block;
      background: #f1f5f9;
      color: #334155;
      font-size: 0.7rem;
      padding: 0.15rem 0.45rem;
      border-radius: 12px;
      margin-right: 0.25rem;
      margin-bottom: 0.2rem;
      border: 1px solid #e2e8f0;
    }}

    .rating-stars {{
      color: #eab308;
      font-size: 0.95rem;
      letter-spacing: 0.05em;
    }}

    .rating-num {{
      font-size: 0.75rem;
      color: var(--text-muted);
    }}

    .text-success {{ color: var(--success-green); }}
    .text-danger {{ color: var(--danger-red); }}
    .text-muted {{ color: var(--text-muted); }}
    .text-center {{ text-align: center; }}
    .font-semibold {{ font-weight: 600; }}

    /* Empty state */
    .empty-card {{
      text-align: center;
      padding: 3rem 1rem;
    }}

    .empty-icon {{
      font-size: 2.5rem;
      margin-bottom: 0.5rem;
    }}

    /* Alerts */
    .alert {{
      padding: 1rem 1.25rem;
      border-radius: 8px;
      margin-bottom: 1.5rem;
      font-size: 0.85rem;
    }}

    .alert-danger {{
      background: var(--danger-bg);
      color: var(--danger-red);
      border: 1px solid #fecaca;
    }}

    .alert ul {{
      margin-top: 0.5rem;
      margin-left: 1.5rem;
    }}

    /* Footer */
    .footer {{
      text-align: center;
      font-size: 0.8rem;
      color: var(--text-muted);
      margin-top: 2rem;
      padding-top: 1.5rem;
      border-top: 1px solid var(--border-color);
    }}

    @media (max-width: 1000px) {{
      .kpi-grid {{ grid-template-columns: repeat(3, minmax(0, 1fr)); }}
    }}
    @media (max-width: 768px) {{
      .kpi-grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .header {{
        flex-direction: column;
        align-items: flex-start;
        gap: 1rem;
      }}
      .header-right {{
        align-items: flex-start;
      }}
      .flow-arrow {{
        display: none;
      }}
      .flow-node {{
        min-width: 100%;
      }}
    }}
  </style>
</head>
<body>
  <div class="container">
    <!-- Header -->
    <header class="header">
      <div class="header-left">
        <h1>Python Web Scraping & Data Extraction System</h1>
        <p>Production Data Pipeline Run Verification & Dashboard</p>
      </div>
      <div class="header-right">
        <div>
          <span class="badge {status_badge_class}"
                style="font-size: 0.85rem; padding: 0.35rem 0.75rem;">
            Run Status: {overall_status.upper()}
          </span>
        </div>
        <div class="header-meta">Report Generated: {generated_time}</div>
      </div>
    </header>

    {error_box_html}

    <!-- KPI Summary Grid -->
    <section class="kpi-grid">
      <div class="kpi-card">
        <div class="kpi-label">Extracted Records</div>
        <div class="kpi-value">{total_extracted:,}</div>
        <div class="kpi-sub">Total parsed items</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">Valid / Accepted</div>
        <div class="kpi-value text-success">{total_accepted:,}</div>
        <div class="kpi-sub">Passed schema validation</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">Invalid Records</div>
        <div class="kpi-value {"text-danger" if total_invalid else ""}">{total_invalid:,}</div>
        <div class="kpi-sub">Rejected by schema</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">Duplicates Dropped</div>
        <div class="kpi-value">{total_duplicates:,}</div>
        <div class="kpi-sub">SHA-256 deduplicated</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">Pages Processed</div>
        <div class="kpi-value">{total_pages:,}</div>
        <div class="kpi-sub">{total_retries} bounded retries</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">Elapsed Time</div>
        <div class="kpi-value">{_format_elapsed(total_elapsed)}</div>
        <div class="kpi-sub">Total execution time</div>
      </div>
    </section>

    <!-- Architecture & Pipeline Flow Card -->
    <section class="card">
      <div class="card-header">
        <h3 class="card-title">Architecture Pipeline Flow</h3>
        <span class="card-subtitle">Deterministic 6-Stage Extraction Lifecycle</span>
      </div>
      <div class="flow-container">
        <div class="flow-node">
          <div class="flow-step">Stage 1</div>
          <div class="flow-name">Web Sources</div>
          <div class="flow-desc">Books (Static) / Quotes (JS)</div>
        </div>
        <div class="flow-arrow">→</div>
        <div class="flow-node">
          <div class="flow-step">Stage 2</div>
          <div class="flow-name">Scraper Engine</div>
          <div class="flow-desc">Scrapy / Selenium WebDriver</div>
        </div>
        <div class="flow-arrow">→</div>
        <div class="flow-node">
          <div class="flow-step">Stage 3</div>
          <div class="flow-name">Normalization</div>
          <div class="flow-desc">Decimal, Rating, Whitespace</div>
        </div>
        <div class="flow-arrow">→</div>
        <div class="flow-node">
          <div class="flow-step">Stage 4</div>
          <div class="flow-name">Validation</div>
          <div class="flow-desc">Pydantic v2 Typed Schemas</div>
        </div>
        <div class="flow-arrow">→</div>
        <div class="flow-node">
          <div class="flow-step">Stage 5</div>
          <div class="flow-name">Deduplication</div>
          <div class="flow-desc">SHA-256 Fingerprint Filter</div>
        </div>
        <div class="flow-arrow">→</div>
        <div class="flow-node">
          <div class="flow-step">Stage 6</div>
          <div class="flow-name">Exporters</div>
          <div class="flow-desc">CSV / JSON / PostgreSQL</div>
        </div>
      </div>
    </section>

    <!-- Runs Overview Card -->
    <section class="card">
      <div class="card-header">
        <div class="card-title-group">
          <h3 class="card-title">Execution Runs</h3>
          <span class="badge badge-primary">{len(runs)} Run{"s" if len(runs) != 1 else ""}</span>
        </div>
        <span class="card-subtitle">Source targets, processing metrics, and destinations</span>
      </div>
      <div class="table-responsive">
        <table class="data-table">
          <thead>
            <tr>
              <th>#</th>
              <th>Run ID</th>
              <th>Source</th>
              <th>Status</th>
              <th>Started</th>
              <th>Pages</th>
              <th>Extracted</th>
              <th>Accepted</th>
              <th>Invalid</th>
              <th>Dups</th>
              <th>Retries</th>
              <th>Elapsed</th>
              <th>Format</th>
              <th>Destination Path</th>
            </tr>
          </thead>
          <tbody>
            {run_table_html}
          </tbody>
        </table>
      </div>
    </section>

    <!-- Sample Data Tables -->
    {books_section_html}
    {quotes_section_html}
    {empty_records_html}

    <!-- Technology Stack Card -->
    <section class="card">
      <div class="card-header">
        <h3 class="card-title">Engineering Stack & Standards</h3>
        <span class="card-subtitle">Technologies used across the system</span>
      </div>
      <div class="stack-grid">
        <span class="tech-pill">🐍 Python 3.12+</span>
        <span class="tech-pill">🕷️ Scrapy (Static Crawling)</span>
        <span class="tech-pill">🌐 Selenium WebDriver (Dynamic JS)</span>
        <span class="tech-pill">🥣 BeautifulSoup4 (DOM Parsing)</span>
        <span class="tech-pill">🛡️ Pydantic v2 (Data Validation)</span>
        <span class="tech-pill">🐘 PostgreSQL & SQLAlchemy (Persistence)</span>
        <span class="tech-pill">📦 Docker & Docker Compose</span>
        <span class="tech-pill">🧪 Pytest & HTML Fixtures</span>
        <span class="tech-pill">⚡ Typer / Click (CLI)</span>
      </div>
    </section>

    <!-- Footer -->
    <footer class="footer">
      <p>Python Web Scraping & Data Extraction System</p>
      <p style="margin-top: 0.35rem;">
        Ethical Scraping Practice: Targets public testing sandbox domains with polite pacing.
      </p>
    </footer>
  </div>
</body>
</html>
"""

    dest_path.write_text(html, encoding="utf-8")
    return dest_path
