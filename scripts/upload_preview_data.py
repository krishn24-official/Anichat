"""Copy what was entered in the local admin preview (frontend/.preview-store.json) into the
real cloud store (Upstash), so nothing has to be typed again after deploying.

    python -m scripts.upload_preview_data            # show what would be copied
    python -m scripts.upload_preview_data --apply    # copy it

Fields, movie records and free entries are copied. Something with the same id already in the
cloud is left alone (the cloud wins), so running it twice is safe. Movies are copied as "not
synced": run scripts/sync_submissions.py afterwards (it rebuilds the same documents).
Needs KV_REST_API_URL and KV_REST_API_TOKEN in .env (the Upstash store connected on Vercel).
"""

import argparse
import json
from pathlib import Path

from anichat import config
from anichat.infrastructure.submission_store import FIELDS_KEY, RECORDS_KEY, SUBMISSIONS_KEY, SubmissionStore

PREVIEW = Path(__file__).resolve().parents[1] / "frontend" / ".preview-store.json"


def main(apply: bool) -> None:
    """Compare the preview's data with the cloud and copy what the cloud lacks.

    Called by: this file's __main__ block (command line)
    """
    if not PREVIEW.exists():
        raise SystemExit(f"no preview data at {PREVIEW}")
    hashes = json.loads(PREVIEW.read_text(encoding="utf-8")).get("hashes", {})
    if "localhost" in (config.KV_REST_API_URL or "") or not config.KV_REST_API_URL:
        raise SystemExit("KV_REST_API_URL in .env must be the Upstash store (from Vercel), not the local preview")
    cloud = SubmissionStore(config.KV_REST_API_URL, config.KV_REST_API_TOKEN)
    try:
        for key, what in ((FIELDS_KEY, "field"), (RECORDS_KEY, "movie"), (SUBMISSIONS_KEY, "entry")):
            items = hashes.get(key, {})
            present = set((cloud._command("HKEYS", key) or []))
            for item_id, value in items.items():
                title = json.loads(value).get("title") or json.loads(value).get("label") or item_id
                if item_id in present:
                    print(f"  skip   {what} {title} (already in the cloud)")
                    continue
                print(f"  {'copy' if apply else 'would copy'}   {what} {title}")
                if apply:
                    cloud._command("HSET", key, item_id, value)
        if not apply:
            print("\nNothing was changed: run again with --apply to copy.")
        else:
            print("\nDone. Now run: python -m scripts.sync_submissions")
    finally:
        cloud.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="copy (without it: only show)")
    main(parser.parse_args().apply)
