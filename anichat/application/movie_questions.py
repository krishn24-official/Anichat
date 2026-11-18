"""Use case: answer ranking / filtering / adding-up questions about movies from the movies table.

    question -> looks structured? -> model plans a MovieQuery (JSON) -> MovieDB runs it
             -> the rows become one more source (a Chunk) for the answer, cited like any other
"""

import time

from anichat.application.llm_fallback import AllModelsUnavailable
from anichat.domain.added import MOVIES
from anichat.domain.chunking import Chunk
from anichat.domain.llm import ChatModel, ModelUnavailable
from anichat.domain.movie_query import describe_query, looks_structured, parse_query, planner_messages
from anichat.domain.records import format_value, parse_fields
from anichat.infrastructure.movie_db import MovieDB

SHOWN_VALUES = 8  # values listed per movie besides the sorted one


class MovieQuestions:
    """Created by: anichat/container.py  answer_service()
    Used by:    application/answer.py  AnswerService._context()
    """

    def __init__(self, db: MovieDB, model: ChatModel):
        self._db = db
        self._model = model

    def source(self, question: str, series: str | None) -> tuple[Chunk | None, float]:
        """The movies table's answer to the question as a source chunk (None when the question isn't
        that kind, the table doesn't exist yet, or nothing matches), and the seconds it took.

        Called by: application/answer.py  AnswerService._context()
        """
        if series not in (None, MOVIES) or not self._db.exists() or not looks_structured(question):
            return None, 0.0
        started = time.perf_counter()
        fields = self._db.fields()
        try:
            reply = self._model.complete(planner_messages(question, fields))
        except (AllModelsUnavailable, ModelUnavailable):
            return None, time.perf_counter() - started
        query = parse_query(reply.text, fields)
        if query is None:
            return None, time.perf_counter() - started
        movies, total, note = self._db.run(query)
        if not movies:
            return None, time.perf_counter() - started
        chunk = Chunk(id=f"{MOVIES}:table", text=results_text(query, movies, total, fields, note), series=MOVIES,
                      kind="table", title="Movies table", display_title="Movies table (your movie records)",
                      section=describe_query(query, {f["id"]: f["label"] for f in fields}), number=None, source="")
        return chunk, time.perf_counter() - started


def results_text(query, movies: list[dict], total: int, fields: list[dict], note: str = "") -> str:
    """The rows as a numbered list the answer model can read and cite.

    Called by: MovieQuestions.source(); tests
    """
    by_id = parse_fields(fields)
    labels = {f["id"]: f["label"] for f in fields}
    lines = [f"Movies table › {describe_query(query, labels)}",
             f"{total} movie(s) match" + (f"; the first {len(movies)} are listed" if total > len(movies) else "")
             + (f" ({note}: listed by release date)" if note else "") + ":"]
    for i, m in enumerate(movies, 1):
        head = f"{i}. {m['title']}" + (f" ({m['year']})" if m.get("year") else "")
        details = []
        if query.sort_by and query.sort_by in m["values"] and query.sort_by in by_id:
            details.append(f"{by_id[query.sort_by].label}: {format_value(by_id[query.sort_by], m['values'][query.sort_by])}")
        elif query.sort_by in ("year", "release_date", "runtime") and m.get(query.sort_by):
            details.append(f"{query.sort_by.replace('_', ' ')}: {m[query.sort_by]}" + (" minutes" if query.sort_by == "runtime" else ""))
        if m.get("days") is not None:
            f = by_id.get(query.days_field)
            amount = (lambda v: format_value(f, v)) if f else str  # noqa: E731
            details.append(f"{len(m['days'])} day rows add up to {amount(m['days_sum'])}: "
                           + "; ".join(f"{label} {amount(v)}" for label, v in m["days"]))
        if m.get("person_roles"):
            details.append("; ".join(m["person_roles"]))
        others = [(fid, v) for fid, v in m["values"].items() if fid != query.sort_by and fid in by_id
                  and by_id[fid].type in ("money", "number", "text", "list", "date")][:SHOWN_VALUES]
        details += [f"{by_id[fid].label}: {format_value(by_id[fid], v)}" for fid, v in others]
        if m.get("directors"):
            details.append("directed by " + ", ".join(m["directors"]))
        if m.get("cast"):
            details.append("starring " + ", ".join(m["cast"]))
        lines.append(head + " | " + " | ".join(details))
    return "\n".join(lines)
