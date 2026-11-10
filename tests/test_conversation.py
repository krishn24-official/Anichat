"""Tests for follow-up questions: detection, history in the prompt, retrieval context (fakes only)."""

from anichat.application.answer import AnswerService
from anichat.domain.answering import build_messages
from anichat.domain.conversation import MAX_TURNS, Turn, looks_like_follow_up, recent
from anichat.domain.llm import ModelReply
from tests.test_answer import AKAZA, EP33


def test_follow_up_questions_are_recognised():
    for q in ("Who killed him?", "What about Vegeta?", "And his brother?", "Why did she leave?"):
        assert looks_like_follow_up(q), q
    for q in ("Who is Goku?", "What happens in episode 1?", "Who killed Cell?"):
        assert not looks_like_follow_up(q), q


def test_history_goes_into_the_prompt_without_old_citations():
    history = [Turn("Who is Akaza?", "Akaza is Upper Rank Three [1][2].")]
    messages = build_messages("Who killed him?", [EP33], history)
    assert [m.role for m in messages] == ["system", "user", "assistant", "user"]
    assert messages[2].content == "Akaza is Upper Rank Three."
    assert "Earlier messages" in messages[0].content
    assert "Earlier messages" not in build_messages("Who is Akaza?", [EP33])[0].content


def test_only_recent_complete_turns_are_kept():
    turns = [Turn(f"q{i}", f"a{i}") for i in range(6)] + [Turn("unanswered", "")]
    assert [t.question for t in recent(turns)] == [f"q{i}" for i in range(6 - MAX_TURNS, 6)]


class RecordingRetrieval:
    def __init__(self):
        self.contexts = []

    def retrieve(self, question, series=None, limit=5, context=""):
        from anichat.application.retrieve import Retrieval, RetrievedChunk
        self.contexts.append(context)
        return Retrieval(question, [RetrievedChunk(AKAZA, 1.0, "search")], {"total": 0.1})


class EchoModel:
    name = "echo"

    def __init__(self):
        self.messages = None

    def complete(self, messages):
        self.messages = messages
        return ModelReply("He was killed by Tanjiro [1].", "echo")


def test_a_follow_up_is_searched_with_the_previous_question():
    retrieval, model = RecordingRetrieval(), EchoModel()
    service = AnswerService(retrieval, model)
    history = [Turn("Who is Akaza?", "Akaza is Upper Rank Three [1].")]
    service.answer("Who killed him?", history=history)
    service.answer("Who is Doma?", history=history)  # names someone new: searched alone
    assert retrieval.contexts == ["Who is Akaza?", ""]
    assert len(model.messages) == 4  # system, earlier question + answer, sources + question
