"""Free entries from the admin form ("Other entries": facts about an anime character, a series,
anything else), as documents. Pure Python, no I/O. Movies are editable records instead
(domain/records.py).

Entries become ordinary Documents of kind "added" (never colliding with the wiki's page of the
same name), saved under data/added/ (not data/documents/, which a wiki rebuild deletes) and
chunked together with the series' wiki documents.
"""

import re
from dataclasses import dataclass, field

from anichat.domain.documents import Document

MOVIES = "movies"  # the series movie records are indexed under
TMDB_LICENSE = "TMDb (themoviedb.org); this product uses the TMDB API but is not endorsed or certified by TMDB"
ADDED_LICENSE = "added by hand"
SUBMISSION_TYPES = ("movie", "anime", "series", "other")
MAX_FACTS = 40
MAX_TEXT = 20_000


@dataclass
class Submission:
    """One free entry from the admin form.

    Created by: parse_submission()
    Used by:    application/added_data.py  AddedDataService.apply()
    """

    id: str
    type: str  # one of SUBMISSION_TYPES
    series: str  # where it belongs: "naruto", "other"...
    title: str  # what it is about: "Naruto Uzumaki"
    facts: dict[str, str] = field(default_factory=dict)  # field label -> value
    notes: str = ""
    source: str = ""  # where the facts come from (a URL)
    submitted_at: str = ""


def _clean(text: object, limit: int) -> str:
    """A form value as one tidy string (no control characters), at most `limit` characters.

    Called by: parse_submission()
    """
    text = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", str(text or "")).strip()
    return text[:limit]


def parse_submission(raw: dict) -> Submission:
    """Validate one stored entry (the form checked it too). Raises ValueError with the reason.

    Called by: application/added_data.py  AddedDataService.apply(); scripts/sync_submissions.py --dry-run
    """
    kind = _clean(raw.get("type"), 20).lower()
    if kind not in SUBMISSION_TYPES:
        raise ValueError(f"unknown type {kind!r}")
    title = _clean(raw.get("title"), 200)
    if not title:
        raise ValueError("missing title")
    series = re.sub(r"[^a-z0-9_]", "_", _clean(raw.get("series"), 60).lower()).strip("_") or (MOVIES if kind == "movie" else "")
    if not series:
        raise ValueError("missing series")
    facts = {}
    for key, value in list((raw.get("facts") or {}).items())[:MAX_FACTS]:
        key, value = _clean(key, 60).lower(), _clean(value, 2000)
        if key and value:
            facts[key] = value
    notes = _clean(raw.get("notes"), MAX_TEXT)
    if not facts and not notes:
        raise ValueError("nothing to add: no facts or notes")
    return Submission(id=_clean(raw.get("id"), 64), type=kind, series=series, title=title, facts=facts, notes=notes,
                      source=_clean(raw.get("source"), 500), submitted_at=_clean(raw.get("submitted_at"), 40))


def added_document(sub: Submission, series_title: str, existing: Document | None = None) -> Document:
    """An entry as a Document (kind "added"), merged into an earlier entry about the same thing:
    newer facts win, notes add up.

    Called by: application/added_data.py  AddedDataService.apply()
    """
    facts = {**(existing.facts if existing else {}), **sub.facts}
    if sub.source:
        facts["added from"] = sub.source
    notes = sub.notes
    if existing and existing.body:
        notes = existing.body + (f"\n\n{sub.notes}" if sub.notes and sub.notes not in existing.body else "")
    body = notes or f"{sub.title}: details added by hand."
    return Document(series=sub.series, series_title=series_title, kind="added", title=sub.title,
                    display_title=sub.title, source_url=sub.source if sub.source.startswith("http") else "",
                    revision_id=0, facts=facts, mentions=[], body=body, license=ADDED_LICENSE)
