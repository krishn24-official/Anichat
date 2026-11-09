"""Measure end-to-end answer quality on the question set (retrieval + LLM).

    python -m scripts.evaluate_answers --series demon_slayer
    python -m scripts.evaluate_answers --series demon_slayer --pause 25 --limit 5

For each question in evals/<series>.json:
  found    - an expected page was among the chunks given to the model (retrieval worked)
  correct  - the answer contains one of `answer_contains` (case-insensitive)
  cited    - one of the answer's sources is an expected page
  refused  - the model said it didn't have the information

Free tiers are small (Gemini ~20 requests/day for this model, Groq ~8k tokens/minute),
so questions are spaced by --pause seconds and a "busy" answer is retried once after a
minute. Full results are saved to data/evals/ for review.
"""

import argparse
import json
import time
from datetime import datetime
from pathlib import Path

from anichat import container
from anichat.application.answer import BUSY_ANSWER
from anichat.domain.series import SERIES

ROOT = Path(__file__).resolve().parents[1]
REFUSAL_PHRASES = ("don't have that information", "do not have that information", "couldn't find", "not in the sources")


def is_expected(title: str, expected: list[str]) -> bool:
    """Whether a page title is one of the expected pages. "Episode 33: Set Your Heart Ablaze"
    matches "Episode 33" but "Episode 3" must not match "Episode 33".

    Called by: score()
    """
    # "Chapter 245: Naruto's Homecoming!!" also matches the page title "Naruto's Homecoming!!"
    return any(title == e or title.startswith(e + ":") or title.endswith(": " + e) for e in expected)


def score(case: dict, answer, retrieved_titles: list[str]) -> dict:
    """Checks for one answered question.

    Called by: main()
    """
    text = answer.text.lower().replace("’", "'")  # models often write "don’t" with a curly apostrophe
    return {
        "question": case["question"],
        "found": any(is_expected(t, case["expect"]) for t in retrieved_titles),
        "correct": any(k in text for k in case["answer_contains"]),
        "cited": any(is_expected(s.title, case["expect"]) for s in answer.sources),
        "refused": any(p in text for p in REFUSAL_PHRASES),
        "model": answer.model,
        "seconds": round(sum(answer.timings.values()), 2),
        "answer": answer.text,
        "sources": [s.title + (f" › {s.section}" if s.section else "") for s in answer.sources],
    }


def main(series_id: str, pause: float, limit: int | None) -> None:
    """Answer every question, print a line per question and the totals, save the details.

    Called by: this file's __main__ block (command line)
    """
    cases = json.loads((ROOT / "evals" / f"{series_id}.json").read_text(encoding="utf-8"))[:limit]
    service = container.answer_service()
    retrieval = service._retrieval  # same retrieval the answers use, to report what the model saw
    results = []
    try:
        print(f"{len(cases)} questions, models: {container.chat_model().name}\n")
        print(f"{'found':>5} {'correct':>7} {'cited':>5} {'refused':>7}  {'model':28} question")
        for i, case in enumerate(cases):
            if i:
                time.sleep(pause)
            answer = service.answer(case["question"], series=series_id)
            if answer.text == BUSY_ANSWER:  # every model rate-limited: wait a minute, try once more
                time.sleep(60)
                answer = service.answer(case["question"], series=series_id)
            titles = [r.chunk.title for r in retrieval.retrieve(case["question"], series=series_id).chunks]
            r = score(case, answer, titles)
            results.append(r)
            mark = lambda ok: "yes" if ok else "-"  # noqa: E731
            print(f"{mark(r['found']):>5} {mark(r['correct']):>7} {mark(r['cited']):>5} {mark(r['refused']):>7}  "
                  f"{(r['model'] or 'none'):28} {r['question']}")
    finally:
        container.index().close()

    n = len(results)
    if not n:
        return
    total = lambda key: sum(r[key] for r in results)  # noqa: E731
    print(f"\nfound {total('found')}/{n} | correct {total('correct')}/{n} | cited the right page "
          f"{total('cited')}/{n} | refused {total('refused')}/{n} | avg {sum(r['seconds'] for r in results) / n:.1f}s")
    out = ROOT / "data" / "evals" / f"answers_{series_id}_{datetime.now():%Y%m%d_%H%M%S}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Details: {out}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--series", required=True, choices=sorted(SERIES))
    parser.add_argument("--pause", type=float, default=20, help="seconds between questions (free-tier limits)")
    parser.add_argument("--limit", type=int, help="only the first N questions")
    args = parser.parse_args()
    main(args.series, args.pause, args.limit)
