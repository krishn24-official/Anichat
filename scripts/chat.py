"""Chat with AniChat in the terminal (same pipeline as the API, no server needed).

    python -m scripts.chat "How did Rengoku die?"
    python -m scripts.chat                     # interactive: type questions, empty line to quit
"""

import sys

from anichat import container
from anichat.application.answer import Answer
from anichat.domain.conversation import Turn


def show(answer: Answer) -> None:
    """Print an answer, its sources and where the time went.

    Called by: main()
    """
    print(f"\n{answer.text}\n")
    for s in answer.sources:
        section = f" › {s.section}" if s.section else ""
        print(f"  {''.join(f'[{n}]' for n in s.numbers)} {s.title}{section}  {s.url}")
    times = ", ".join(f"{k} {v:.2f}s" for k, v in answer.timings.items())
    print(f"\n  ({answer.model or 'no model'}; {times})\n")


def main(question: str | None) -> None:
    """Answer one question from the command line, or loop over typed questions.

    Called by: this file's __main__ block (command line)
    """
    service = container.answer_service()
    try:
        if question:
            show(service.answer(question))
            return
        history: list[Turn] = []  # the conversation so far: follow-ups ("who is his brother?") work
        while (q := input("You: ").strip()):
            answer = service.answer(q, history=history)
            show(answer)
            history.append(Turn(q, answer.text))
    finally:
        container.index().close()


if __name__ == "__main__":
    main(" ".join(sys.argv[1:]) or None)
