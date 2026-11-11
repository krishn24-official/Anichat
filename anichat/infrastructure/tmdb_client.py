"""TMDb (The Movie Database) API client: movie search and details, one movie at a time.

Auth: a v4 "API Read Access Token" (TMDB_READ_TOKEN, sent as a Bearer header) or a v3
"API Key" (TMDB_API_KEY, sent as ?api_key=). Both come free with a themoviedb.org account
(Settings -> API).
"""

import time

import httpx

API = "https://api.themoviedb.org/3"
USER_AGENT = "AniChat/0.1 (personal, non-commercial project)"
RETRIES = 3


class TmdbClient:
    """Created by: application/added_data.py users (scripts/add_movie.py, scripts/sync_submissions.py)
    Used by:    application/added_data.py  AddedDataService
    """

    def __init__(self, read_token: str | None = None, api_key: str | None = None):
        if not (read_token or api_key):
            raise ValueError("TMDb needs TMDB_READ_TOKEN or TMDB_API_KEY in .env (free: themoviedb.org -> Settings -> API)")
        headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
        if read_token:
            headers["Authorization"] = f"Bearer {read_token}"
        self._key = None if read_token else api_key
        self._http = httpx.Client(timeout=20, headers=headers)

    def close(self) -> None:
        """Close the HTTP connection. Called by: the scripts when done"""
        self._http.close()

    def _get(self, path: str, **params) -> dict:
        """One API call, retried on rate limits (429) and server errors.

        Called by: search_movie(), movie()
        """
        if self._key:
            params["api_key"] = self._key
        for attempt in range(RETRIES):
            r = self._http.get(f"{API}{path}", params=params)
            if r.status_code == 200:
                return r.json()
            if r.status_code == 401:
                raise PermissionError("TMDb rejected the key/token (HTTP 401): check TMDB_READ_TOKEN / TMDB_API_KEY")
            if r.status_code == 404:
                raise LookupError(f"TMDb has no {path}")
            if r.status_code not in (429, 500, 502, 503, 504):
                r.raise_for_status()
            time.sleep(float(r.headers.get("Retry-After", 2 * (attempt + 1))))
        r.raise_for_status()
        return {}

    def search_movie(self, title: str, year: int | None = None) -> list[dict]:
        """Matching movies, best first: [{"id", "title", "release_date", "popularity", ...}].

        Called by: application/added_data.py  AddedDataService.find_movie()
        """
        params = {"query": title, "include_adult": "false"}
        if year:
            params["primary_release_year"] = year
        return self._get("/search/movie", **params).get("results", [])

    def movie(self, tmdb_id: int) -> dict:
        """Full details of one movie, with its cast and crew ("credits").

        Called by: application/added_data.py  AddedDataService.add_movie()
        """
        return self._get(f"/movie/{tmdb_id}", append_to_response="credits")
