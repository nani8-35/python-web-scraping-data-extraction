"""Rebuild the dashboard from previously verified live-run artifacts."""

import json
from pathlib import Path

from scraping_system.models import BookRecord, QuoteRecord, RunMetrics
from scraping_system.reporting.html_report import generate_report


def main() -> None:
    runs = []
    records = []
    for kind, model in (("books", BookRecord), ("quotes", QuoteRecord)):
        run_path = Path(f"sample_output/{kind}_run.json")
        runs.append(RunMetrics.model_validate_json(run_path.read_text(encoding="utf-8")))
        samples = json.loads(Path(f"sample_output/{kind}_sample.json").read_text(encoding="utf-8"))
        records.extend(model.model_validate(raw) for raw in samples)
    path = generate_report(runs, records, Path("artifacts/report.html"))
    print(f"Generated {path} from {len(records)} real records across {len(runs)} runs")


if __name__ == "__main__":
    main()
