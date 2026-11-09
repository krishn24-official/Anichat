"""Quality check for stage 2 output: run after build_documents, before chunking.

    python -m scripts.check_documents --series death_note

Reports (and exits with code 1 if any check fails):
  - leftover wiki markup in document bodies ({{ }}, [[ ]], HTML tags, table syntax)
  - episodes/chapters without a number (exact "episode 5" lookups need it; a few specials are normal)
  - pages whose first line is not a real paragraph (stray tab names, quotes...)
"""

import argparse
import re
import sys
from pathlib import Path

from anichat.domain.series import SERIES
from anichat.infrastructure.document_store import DocumentStore

DOCS = Path(__file__).resolve().parents[1] / "data" / "documents"
MARKUP = {"{{ or }}": r"\{\{|\}\}", "[[ or ]]": r"\[\[|\]\]", "html tag": r"<[a-zA-Z/][^>]*>",
          "table syntax": r"^\s*(\{\||\|\}|\|-)", "image markup": r"thumb\||\d+px\|"}


def main(series_id: str) -> int:
    """Run all checks over a series' documents and print a report.

    Called by: this file's __main__ block. Returns the exit code (0 = all good).
    """
    docs = list(DocumentStore(DOCS).iter_documents(series_id))
    problems = 0
    print(f"{len(docs)} documents\n")

    for name, pattern in MARKUP.items():
        bad = [d.meta["title"] for d in docs if re.search(pattern, d.body, re.M)]
        # A few pages with unbalanced brackets in the wiki source itself are tolerated (One Piece:
        # 5 of 4,125); more than that means the cleaner is missing a construct.
        failing = len(bad) > max(2, len(docs) * 0.002)
        problems += failing
        print(f"{'FAIL' if failing else ('note' if bad else 'ok'):4}  leftover {name}: {len(bad)} documents {bad[:4]}")

    numbered = [d for d in docs if d.meta.get("kind") in ("episode", "chapter")]
    missing = [d.meta["title"] for d in numbered if d.meta.get("number") is None]
    # Specials (one-shots, omake, recap pages) have no number: a few are normal, many are a bug.
    too_many = len(missing) > max(2, len(numbered) * 0.15)  # Demon Slayer has ~10% bonus chapters
    problems += too_many
    status = "FAIL" if too_many else ("note" if missing else "ok")
    print(f"{status:4}  episodes/chapters without a number: {len(missing)}/{len(numbered)} {missing[:30]}")

    stray = []
    for d in docs:
        after_credit = d.body.split("(CC BY-SA 3.0)", 1)[-1].strip()
        first = after_credit.split("\n", 1)[0].strip()
        # A short real sentence ("Eddie is a member of the Mafia.") is fine; a short fragment is not.
        if first and not first.startswith("## ") and len(first) < 40 and not first.endswith((".", "!", "?", ")")):
            stray.append(f"{d.meta['title']}: {first!r}")
    # A few short first lines are normal (stub-like pages); many mean a cleaning problem.
    warn = len(stray) > max(3, len(docs) // 50)
    print(f"{'WARN' if warn else 'ok':4}  short first line (possible stray text): {len(stray)} {stray[:4]}")
    return 1 if problems else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--series", required=True, choices=sorted(SERIES))
    sys.exit(main(parser.parse_args().series))
