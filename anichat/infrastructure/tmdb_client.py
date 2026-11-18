"""TMDb (The Movie Database) API client: movie search and details, one movie at a time.

Auth: a v4 "API Read Access Token" (TMDB_READ_TOKEN, sent as a Bearer header) or a v3
"API Key" (TMDB_API_KEY, sent as ?api_key=). Both come free with a themoviedb.org account
(Settings -> API).
"""

import re
import time

import httpx

API = "https://api.tmdb.org/3"  # TMDb's alias of api.themoviedb.org, which some Indian ISPs block
USER_AGENT = "AniChat/0.1 (personal, non-commercial project)"
RETRIES = 3


class TmdbClient:
    """Created by: application/added_data.py users (scripts/add_movie.py, scripts/sync_submissions.py)
    Used by:    application/added_data.py  AddedDataService
    """

    def __init__(self, read_token: str | None = None, api_key: str | None = None):
        if not (read_token or api_key):
            raise ValueError("TMDb needs TMDB_READ_TOKEN or TMDB_API_KEY in .env (free: themoviedb.org -> Settings -> API)")
        # Either kind works in either setting: a 32-character v3 "API Key" goes as ?api_key=, the
        # long v4 "Read Access Token" as a Bearer header.
        given = [v for v in (read_token, api_key) if v]
        self._key = next((v for v in given if re.fullmatch(r"[0-9a-fA-F]{32}", v)), None)
        headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
        if not self._key:
            headers["Authorization"] = f"Bearer {given[0]}"
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

        Called by: scripts/add_movie.py
        """
        params = {"query": title, "include_adult": "false"}
        if year:
            params["primary_release_year"] = year
        return self._get("/search/movie", **params).get("results", [])

    def movie(self, tmdb_id: int) -> dict:
        """Full details of one movie, with its cast and crew ("credits").

        Called by: scripts/add_movie.py
        """
        return self._get(f"/movie/{tmdb_id}", append_to_response="credits")

    def collection(self, name_or_id: str) -> tuple[str, list[dict]]:
        """A film series ("Jumanji Collection", or its id): (its name, its movies).

        Called by: scripts/add_movie.py --collection
        """
        if not str(name_or_id).isdigit():
            found = self._get("/search/collection", query=name_or_id).get("results", [])
            if not found:
                raise LookupError(f"TMDb has no collection {name_or_id!r}")
            name_or_id = found[0]["id"]
        data = self._get(f"/collection/{name_or_id}")
        return data["name"], data.get("parts", [])

    def directed_by(self, name: str) -> tuple[str, list[dict]]:
        """The movies a person directed: (their name as on TMDb, the movies).

        Called by: scripts/add_movie.py --director
        """
        people = self._get("/search/person", query=name).get("results", [])
        if not people:
            raise LookupError(f"TMDb has no person {name!r}")
        person = max(people[:5], key=lambda p: p.get("popularity", 0))
        crew = self._get(f"/person/{person['id']}/movie_credits").get("crew", [])
        return person["name"], [c for c in crew if c.get("job") == "Director"]

    def by_companies(self, company_ids: str, released_before: str, min_votes: int = 100, max_pages: int = 20) -> list[dict]:
        """Movies a studio made ("420|7505": any of these TMDb company ids), released by a date,
        with at least `min_votes` votes (leaves out obscure releases), oldest first.

        Called by: scripts/add_movie.py --company
        """
        movies, page = [], 1
        while page <= max_pages:
            data = self._get("/discover/movie", with_companies=company_ids, page=page, include_adult="false",
                             sort_by="primary_release_date.asc", **{"primary_release_date.lte": released_before,
                                                                     "vote_count.gte": min_votes})
            movies += data.get("results", [])
            if page >= data.get("total_pages", 1):
                break
            page += 1
        return movies
