import csv
from pathlib import Path


def read_csv_rows(path: Path, limit: int = 50) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    return rows[-limit:]


def total_cost(rows: list[dict[str, str]]) -> float:
    total = 0.0
    for row in rows:
        try:
            total += float(row.get("total_cost_usd", 0) or 0)
        except ValueError:
            continue
    return round(total, 6)
