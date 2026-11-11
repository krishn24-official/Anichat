"""The admin form's data, kept in a cloud Redis (Upstash, free tier) so the form works while
the laptop is off: the Vercel functions (frontend/api/*.ts) write it; scripts/sync_submissions.py
reads it here when the laptop is back.

Keys (the same names as frontend/api/_lib.ts):
- anichat:submissions  hash: entry id -> free entry JSON, with "status" pending/done/error
- anichat:fields       hash: field id -> field definition JSON
- anichat:records      hash: record id -> movie record JSON (edited by the form, versioned)
- anichat:synced       hash: record id -> the version the laptop has indexed
Upstash's REST API is used directly (no Redis client library needed).
"""

import json

import httpx

SUBMISSIONS_KEY = "anichat:submissions"
FIELDS_KEY = "anichat:fields"
RECORDS_KEY = "anichat:records"
SYNCED_KEY = "anichat:synced"


class SubmissionStore:
    """Created by: scripts/sync_submissions.py, scripts/add_movie.py
    Used by:    the same scripts
    """

    def __init__(self, url: str | None, token: str | None):
        if not (url and token):
            raise ValueError("the admin form's store needs KV_REST_API_URL and KV_REST_API_TOKEN in .env "
                             "(Upstash Redis: copy them from the Vercel project's Storage tab)")
        self._url = url.rstrip("/")
        self._http = httpx.Client(timeout=30, headers={"Authorization": f"Bearer {token}"})

    def close(self) -> None:
        """Close the HTTP connection. Called by: the scripts"""
        self._http.close()

    def _command(self, *args):
        """Run one Redis command through Upstash's REST API and return its result.

        Called by: every method below
        """
        r = self._http.post(self._url, json=[str(a) for a in args])
        r.raise_for_status()
        body = r.json()
        if "error" in body:
            raise RuntimeError(f"Upstash: {body['error']}")
        return body["result"]

    def _values(self, key: str) -> list[dict]:
        """Every value of a hash, parsed (unreadable ones skipped). Called by: all(), fields(), records()"""
        flat = self._command("HGETALL", key) or []
        out = []
        for value in flat[1::2]:
            try:
                out.append(json.loads(value))
            except json.JSONDecodeError:
                continue
        return out

    # -------------------------------------------------- free entries

    def all(self) -> list[dict]:
        """Every free entry, oldest first. Called by: pending(); scripts/sync_submissions.py --list"""
        return sorted(self._values(SUBMISSIONS_KEY), key=lambda e: e.get("submitted_at", ""))

    def pending(self) -> list[dict]:
        """Free entries not processed yet. Called by: scripts/sync_submissions.py"""
        return [e for e in self.all() if e.get("status", "pending") == "pending"]

    def mark(self, entry: dict, status: str, result: str) -> None:
        """Save an entry's outcome ("done": what was added; "error": why not), shown in the form.

        Called by: scripts/sync_submissions.py
        """
        updated = {**entry, "status": status, "result": result}
        self._command("HSET", SUBMISSIONS_KEY, entry["id"], json.dumps(updated, ensure_ascii=False))

    # -------------------------------------------------- fields and movie records

    def fields(self) -> list[dict]:
        """All field definitions. Called by: scripts/sync_submissions.py, scripts/add_movie.py"""
        return self._values(FIELDS_KEY)

    def records(self) -> list[dict]:
        """All movie records (deleted ones too, until synced). Called by: scripts/sync_submissions.py"""
        return self._values(RECORDS_KEY)

    def has_record(self, record_id: str) -> bool:
        """Called by: scripts/add_movie.py"""
        return bool(self._command("HEXISTS", RECORDS_KEY, record_id))

    def add_record(self, record: dict, now: str) -> None:
        """Store a new movie record (version 1), as the form does for a new one.

        Called by: scripts/add_movie.py
        """
        stored = {**record, "version": 1, "created_at": now, "updated_at": now}
        self._command("HSET", RECORDS_KEY, record["id"], json.dumps(stored, ensure_ascii=False))

    def synced(self) -> dict[str, int]:
        """Record id -> the version last indexed. Called by: scripts/sync_submissions.py"""
        flat = self._command("HGETALL", SYNCED_KEY) or []
        return {flat[i]: int(flat[i + 1]) for i in range(0, len(flat), 2)}

    def mark_synced(self, record: dict) -> None:
        """Remember that this version is indexed (the form then shows it as "in AniChat"); a deleted
        record is removed from the store for good.

        Called by: scripts/sync_submissions.py
        """
        if record.get("deleted"):
            self._command("HDEL", RECORDS_KEY, record["id"])
            self._command("HDEL", SYNCED_KEY, record["id"])
        else:
            self._command("HSET", SYNCED_KEY, record["id"], record["version"])
