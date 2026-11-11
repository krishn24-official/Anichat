"""Write the series ids and names for the admin form's "Series" suggestions.

    python -m scripts.export_series

Output: frontend/src/admin/series.json  (committed: the form on Vercel works without the API)
Run again after adding series to anichat/domain/series.py.
"""

import json
from pathlib import Path

from anichat.domain.series import SERIES

OUT = Path(__file__).resolve().parents[1] / "frontend" / "src" / "admin" / "series.json"


def main() -> None:
    """Write [{"id", "title"}] sorted by name.

    Called by: this file's __main__ block (command line)
    """
    rows = sorted(({"id": k, "title": s.title} for k, s in SERIES.items()), key=lambda r: r["title"].lower())
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(rows, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{len(rows)} series -> {OUT}")


if __name__ == "__main__":
    main()
